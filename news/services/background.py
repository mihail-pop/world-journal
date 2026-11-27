"""Persisted refresh rounds, sleeping workers, and status from saved feed state."""
from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from threading import Condition, Event, Lock, Thread

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, close_old_connections
from django.utils.timezone import localtime

from core.database import database_write, write_transaction
from news.feed_state import snapshot_metadata
from news.models import FeedSchedule, FeedState
from news.preferences import effective_registry, freshness_seconds
from news.types import SourceKind

from .archive import capture_snapshot, maintain_archive
from .cache import cache_lock, fixed_feed_cache_key, google_cache_key, google_pause_until, parse_datetime, record_failure, refresh_jitter, youtube_cache_key
from .country_news import _countries_by_code, _country_for_code, get_country_news, get_world_news
from .regional_news import get_fixed_feed
from .region_routing import eligible_youtube_sources
from .youtube_news import get_youtube_feed

logger = logging.getLogger(__name__)


class ArchiveWriteError(Exception):
    pass


def feed_jobs(registry):
    for feed in registry.feeds:
        if feed.enabled_by_default:
            yield ("rss", feed.id), fixed_feed_cache_key(feed)
    for source in registry.sources:
        if source.enabled_by_default and source.kind is SourceKind.YOUTUBE:
            yield ("youtube", source.id), youtube_cache_key(source)
    google = registry.get("google_news_country")
    if google.enabled_by_default:
        yield ("google", "WORLD"), google_cache_key(google, "WORLD")
        for code in _countries_by_code():
            yield ("google", code), google_cache_key(google, code)


def next_refresh(started_at, interval):
    jitter = refresh_jitter("cycle", {"fetched_at": started_at.isoformat()})
    return started_at + timedelta(seconds=interval + jitter)


class FeedWarmer:
    def __init__(self):
        self.condition = Condition()
        self.refresh_lock = Lock()
        self.started = self.ready = False
        self.registry = None
        self.interval = settings.NEWS_REFRESH_SECONDS
        self.jobs, self.states = {}, {}
        self.refresh_started_at = self.next_refresh_at = self.google_until = None
        self.wake_at = None
        self.reload_requested = True
        self.force_requested = False
        self.maintenance_requested = self.full_cleanup = self.batch_full = False
        self.urgent, self.normal = OrderedDict(), OrderedDict()
        self.running, self.force_jobs = set(), set()
        self.scan_requested = Event()
        self.cycle = {}
        self.cycle_started_at = self.cycle_finished_at = None
        self.manual_refresh = False

    def start(self):
        with self.condition:
            if self.started:
                if self.wake_at and datetime.now(UTC) >= self.wake_at:
                    self.scan_requested.set()
                return
            # Restore compact metadata before a page reads progress. No feed
            # contents or network requests are needed to resume the round.
            self._load_configuration()
            self.reload_requested = False
            self.started = True
            for index in range(settings.NEWS_BACKGROUND_WORKERS):
                Thread(target=self._worker, args=(False,), daemon=True, name=f"feeds-{index}").start()
            Thread(target=self._worker, args=(True,), daemon=True, name="feeds-priority").start()
            Thread(target=self._schedule, daemon=True, name="feeds-refresh").start()

    def snapshot_saved(self, state):
        with self.condition:
            previous = self.states.get(state.cache_key, {})
            self.states[state.cache_key] = {
                "metadata": state.metadata, "expires_at": state.expires_at,
                "archive_stamp": state.archive_stamp or previous.get("archive_stamp", ""),
            }
        self.scan_requested.set()

    def google_cooldown(self, snapshot):
        with self.condition:
            self.google_until = parse_datetime(snapshot.get("retry_after_at"))
        self.scan_requested.set()

    def _enqueue(self, job, *, urgent=False, retry=False, force=False):
        with self.condition:
            if job in self.running:
                return
            if force:
                self.force_jobs.add(job)
            if urgent:
                previous_retry = self.normal.pop(job, False) or self.urgent.get(job, False)
                retry = retry or previous_retry
                self.urgent[job] = retry
                self.urgent.move_to_end(job, last=False)
            elif job not in self.urgent and job not in self.normal:
                self.normal[job] = retry
            self.condition.notify_all()

    def _promote(self, jobs, retry=False):
        # Opening a page only changes the order of work already scheduled.
        with self.condition:
            for job in jobs:
                if job not in self.jobs:
                    continue
                metadata = self.states.get(self.jobs[job], {}).get("metadata", {})
                if job in self.normal or job in self.urgent or retry and metadata.get("last_error"):
                    self._enqueue(job, urgent=True, retry=retry)

    def prioritize(self, code, *, retry=False):
        country = _country_for_code(code)
        self.start()
        with self.condition:
            if self.registry is None:
                return
            jobs = [job for job in self.jobs if job[0] == "rss"]
            jobs += [("youtube", source.id) for source in eligible_youtube_sources(country, self.registry)]
            jobs.append(("google", country["iso_a2"]))
            self._promote(jobs, retry)

    def prioritize_news(self, *, country="WORLD", videos=False):
        self.start()
        with self.condition:
            self._promote([job for job in self.jobs if (
                videos and job[0] == "youtube"
                or not videos and (job[0] == "rss" or job == ("google", country))
            )])

    def busy(self):
        with self.condition:
            return not self.ready or self.force_requested or bool(self.urgent or self.normal or self.running)

    def rescan(self):
        self.start()
        with self.condition:
            self.reload_requested = True
            self.ready = False
        self.scan_requested.set()

    def trim_archive(self):
        self.start()
        with self.condition:
            self.maintenance_requested = self.full_cleanup = True
        self.scan_requested.set()

    def refresh_all(self):
        self.start()
        with self.refresh_lock:
            with self.condition:
                if self.force_requested or self.manual_refresh and self.cycle_finished_at is None:
                    return
            now = datetime.now(UTC)
            with write_transaction():
                schedule = FeedSchedule.objects.filter(pk=1).first()
                if schedule is None:
                    schedule = FeedSchedule(pk=1, cycle_started_at=now, next_refresh_at=next_refresh(now, self.interval))
                schedule.manual_requested = True
                schedule.save()
            with self.condition:
                self.force_requested = True
        self.scan_requested.set()

    def retry_failed(self, kind, source_id):
        self.start()
        with self.condition:
            providers = {feed.id: feed.provider_id for feed in self.registry.feeds}
            matching = [job for job in self.jobs if job[0] == kind and (
                kind == "google" and source_id == "google_news_country"
                or kind == "rss" and providers.get(job[1]) == source_id
                or kind == "youtube" and job[1] == source_id
            )]
            if not matching:
                raise ValueError("This source is switched off or unavailable.")
            active = set(self.running) | self.urgent.keys() | self.normal.keys()
            keys = [self.jobs[job] for job in matching if job not in active
                    and self.states.get(self.jobs[job], {}).get("metadata", {}).get("last_error")]
            already_running = bool(active.intersection(matching))
        if kind == "google":
            paused = google_pause_until(cache, datetime.now(UTC))
            if paused:
                return {"queued": False, "paused_until": paused.isoformat()}
        if not keys:
            return {"queued": already_running}
        queued = False
        # Keep the request across a restart without changing the failure count
        # or pretending another network attempt has already taken place.
        with write_transaction():
            for state in FeedState.objects.filter(cache_key__in=keys):
                if not state.metadata.get("last_error"):
                    continue
                stamp = datetime.now(UTC).isoformat()
                state.metadata = {**state.metadata, "retry_requested_at": stamp, "saved_at": stamp}
                state.save(update_fields=["metadata"])
                queued = True
        if queued:
            self.rescan()
        return {"queued": queued or already_running}

    def _progress_state(self, job):
        state = self.states.get(self.jobs[job], {})
        metadata = state.get("metadata", {})
        attempted = parse_datetime(metadata.get("last_attempt_at"))
        fresh_at_start = (job[0] != "google" and attempted and self.refresh_started_at and not self.manual_refresh
                          and next_refresh(attempted, self.interval) > self.refresh_started_at and not metadata.get("last_error"))
        if self.refresh_started_at and attempted and (attempted >= self.refresh_started_at or fresh_at_start) and not metadata.get("archive_pending"):
            if metadata.get("last_error"):
                return "failed"
            if metadata.get("last_success_at") == state.get("archive_stamp"):
                return "done"
        if job in self.running:
            return "running"
        if job in self.normal or job in self.urgent:
            return "queued"
        return "waiting"

    def progress(self):
        with self.condition:
            self.cycle = {job: self._progress_state(job) for job in self.jobs}
            return {
                "total": len(self.cycle),
                "completed": sum(state in {"done", "failed", "skipped"} for state in self.cycle.values()),
                "failed": sum(state == "failed" for state in self.cycle.values()),
                "busy": self.busy(), "running": list(self.running),
                "failed_jobs": [job for job, state in self.cycle.items() if state == "failed"],
                "started_at": self.cycle_started_at, "finished_at": self.cycle_finished_at,
            }

    def status(self):
        """No SQL, even while the Sources page is watching an active refresh."""
        with self.condition:
            progress = self.progress()
            registry, jobs, states, paused = self.registry, dict(self.jobs), dict(self.states), self.google_until
            now = datetime.now(UTC)
            active = set(self.running) | self.normal.keys() | self.urgent.keys()
            due_times = {job: self._due_at(job, now) for job in self.jobs}
            deadlines = [deadline for job, deadline in due_times.items() if job not in active]
            if self.next_refresh_at and self.cycle_finished_at:
                deadlines.append(self.next_refresh_at)
            next_update = min(deadlines) if deadlines else self.next_refresh_at
        providers = {provider.id: provider for provider in registry.providers} if registry else {}
        feeds = {feed.id: feed for feed in registry.feeds} if registry else {}
        sources = {source.id: source for source in registry.sources} if registry else {}

        def label(job):
            kind, identity = job
            if kind == "google":
                return "Google News · World headlines" if identity == "WORLD" else f"Google News · {_countries_by_code()[identity]['name']}"
            if kind == "rss" and identity in feeds:
                feed = feeds[identity]
                return f"{providers[feed.provider_id].display_name} · {feed.section_label}"
            return sources[identity].display_name if identity in sources else "Updating sources"

        now = datetime.now(UTC)
        problems, errored = OrderedDict(), set()

        def problem_group(job):
            kind, identity = job
            if kind == "google":
                key, name = (kind, "google_news_country"), "Google News"
                scope = "World headlines" if identity == "WORLD" else _countries_by_code()[identity]["name"]
            elif kind == "rss" and identity in feeds:
                feed = feeds[identity]
                key, name = (kind, feed.provider_id), providers[feed.provider_id].display_name
                scope = feed.section_label
            else:
                key, name, scope = job, label(job), ""
            group = problems.setdefault(key, {"name": name, "pause": "", "messages": OrderedDict(), "jobs": set(),
                                              "kind": kind, "source_id": key[1]})
            group["jobs"].add(job)
            return group, scope

        def add_problem(job, message):
            group, scope = problem_group(job)
            scopes = group["messages"].setdefault(message, [])
            if scope and scope not in scopes:
                scopes.append(scope)

        google_paused = paused and paused > now and ("google", "WORLD") in jobs
        if google_paused:
            group, _scope = problem_group(("google", "WORLD"))
            group["pause"] = f"Automatic refresh is paused after a rate-limit response. It resumes after {localtime(paused):%H:%M on %b %d}. Cached headlines remain available."
        missing = 0
        for job, key in jobs.items():
            state = states.get(key, {})
            metadata = state.get("metadata", {})
            if not metadata.get("last_success_at") or metadata.get("item_count") is None or state.get("expires_at", now) <= now:
                missing += 1
            if metadata.get("last_error"):
                add_problem(job, metadata.get("last_error_detail") or metadata["last_error"])
                errored.add(job)
        for job in progress.pop("failed_jobs"):
            if job in jobs and job not in errored:
                if job[0] == "google" and google_paused:
                    continue
                add_problem(job, "The last check could not be completed; cached results are retained where available.")
        errors = []
        for group in problems.values():
            messages = [group["pause"]] if group["pause"] else []
            for message, scopes in group["messages"].items():
                scope = ", ".join(scopes[:5])
                if len(scopes) > 5:
                    scope += f" and {len(scopes) - 5} more"
                if group["pause"] and "HTTP 429" in message:
                    messages.append(f"Rate-limited checks: {scope}.")
                else:
                    messages.append(f"{scope + ': ' if scope else ''}{message.rstrip('. ')}.")
            retrying = bool(active.intersection(group["jobs"])) or any(
                states.get(jobs[job], {}).get("metadata", {}).get("retry_requested_at") for job in group["jobs"]
            )
            retry_at = min(due_times[job] for job in group["jobs"])
            retry_text = ""
            if group["kind"] != "google" and not retrying:
                local_retry = localtime(retry_at)
                when = local_retry.strftime("%H:%M" if local_retry.date() == localtime(now).date() else "%H:%M on %b %d")
                retry_text = f"Automatic retry at {when}"
            errors.append({"name": group["name"], "error": " ".join(messages),
                           "kind": group["kind"], "source_id": group["source_id"],
                           "category": "YouTube" if group["kind"] == "youtube" else "Articles",
                           "retrying": retrying, "retry_disabled": bool(group["pause"]) or retrying,
                           "retry_at": retry_at.isoformat(), "retry_text": retry_text})
        progress["current"] = [label(job) for job in progress.pop("running")]
        progress.pop("started_at")
        return {**progress, "errors": errors, "failed": len(errors), "enabled": len(jobs), "missing": missing,
                "next_update_at": next_update.isoformat() if next_update else None}

    def _load_configuration(self):
        registry, interval = effective_registry(), freshness_seconds()
        jobs = dict(feed_jobs(registry))
        states = {row.cache_key: {"metadata": row.metadata, "expires_at": row.expires_at, "archive_stamp": row.archive_stamp}
                  for row in FeedState.objects.filter(cache_key__in=jobs.values())}
        schedule = FeedSchedule.objects.filter(pk=1).first()
        paused = google_pause_until(cache, datetime.now(UTC))
        if schedule and schedule.next_refresh_at != next_refresh(schedule.cycle_started_at, interval):
            schedule.next_refresh_at = next_refresh(schedule.cycle_started_at, interval)
            with write_transaction():
                schedule.save(update_fields=["next_refresh_at"])
        with self.condition:
            self.registry, self.interval, self.jobs = registry, interval, jobs
            for key, state in states.items():
                previous = self.states.get(key, {}).get("metadata", {})
                previous_saved = parse_datetime(previous.get("saved_at")) or parse_datetime(previous.get("last_attempt_at"))
                loaded_saved = parse_datetime(state["metadata"].get("saved_at")) or parse_datetime(state["metadata"].get("last_attempt_at"))
                if not previous_saved or loaded_saved and loaded_saved >= previous_saved:
                    self.states[key] = state
            self.google_until = max((value for value in (self.google_until, paused) if value), default=None)
            if schedule:
                self.refresh_started_at, self.next_refresh_at = schedule.cycle_started_at, schedule.next_refresh_at
                self.cycle_started_at = schedule.cycle_started_at.isoformat()
                self.cycle_finished_at = schedule.cycle_finished_at.isoformat() if schedule.cycle_finished_at else None
                self.manual_refresh = schedule.cycle_manual
                self.force_requested |= schedule.manual_requested
                self.batch_full = schedule.cycle_finished_at is None
            self.urgent = OrderedDict((job, retry) for job, retry in self.urgent.items() if job in jobs)
            self.normal = OrderedDict((job, retry) for job, retry in self.normal.items() if job in jobs)
            self.cycle = {job: state for job, state in self.cycle.items() if job in jobs}
            self.force_jobs.intersection_update(jobs)
            self.ready = True
            # Queue only an interrupted import, using its saved response. There
            # is no archive replay or feed-content read during startup.
            for job, key in jobs.items():
                if job in self.running:
                    continue
                state = self.states.get(key, {})
                metadata = state.get("metadata", {})
                stamp = metadata.get("last_success_at")
                if stamp and state.get("archive_stamp") != stamp:
                    state["metadata"] = {**metadata, "archive_pending": True,
                        "last_error": metadata.get("last_error") or "Retained coverage is waiting to be saved.",
                        "retry_after_at": metadata.get("retry_after_at") or datetime.now(UTC).isoformat()}
            if self.cycle_finished_at and any(self._progress_state(job) == "waiting" for job in jobs):
                self.cycle_finished_at = None
                self.batch_full = True
            self.condition.notify_all()

    def _begin_cycle(self, now, manual=False):
        with self.refresh_lock:
            with self.condition:
                manual |= self.force_requested
            deadline = next_refresh(now, self.interval)
            with write_transaction():
                FeedSchedule.objects.update_or_create(pk=1, defaults={"cycle_started_at": now,
                    "next_refresh_at": deadline, "cycle_finished_at": None, "cycle_manual": manual, "manual_requested": False})
            with self.condition:
                self.refresh_started_at, self.next_refresh_at = now, deadline
                self.cycle_started_at, self.cycle_finished_at = now.isoformat(), None
                self.manual_refresh, self.batch_full = manual, True
                for job in self.jobs:
                    if self._due_at(job, now, new_cycle=True, manual=manual) <= now:
                        self._enqueue(job, retry=manual, force=True)
                self.force_requested = False

    def _finish_cycle(self):
        with self.refresh_lock:
            with self.condition:
                progress = self.progress()
                if (not self.refresh_started_at or self.cycle_finished_at or self.running or self.normal or self.urgent
                        or progress["completed"] != progress["total"]):
                    return
                started = self.refresh_started_at
            finished = datetime.now(UTC)
            with database_write():
                saved = FeedSchedule.objects.filter(pk=1, cycle_started_at=started).update(cycle_finished_at=finished)
            with self.condition:
                if saved and self.refresh_started_at == started:
                    self.cycle_finished_at = finished.isoformat()
                    self.maintenance_requested = self.full_cleanup = True
                    self.batch_full = False

    def _due_at(self, job, now, *, new_cycle=False, manual=False):
        metadata = self.states.get(self.jobs[job], {}).get("metadata", {})
        attempted = parse_datetime(metadata.get("last_attempt_at"))
        attempted_this_round = attempted and self.refresh_started_at and attempted >= self.refresh_started_at
        manual |= self.manual_refresh and not self.cycle_finished_at and not attempted_this_round
        if metadata.get("retry_requested_at"):
            due = now
        elif metadata.get("last_error") and not manual:
            base = settings.NEWS_GOOGLE_FAILURE_BACKOFF_SECONDS if job[0] == "google" else settings.NEWS_FAILURE_BACKOFF_SECONDS
            due = parse_datetime(metadata.get("retry_after_at")) or (attempted or now) + timedelta(seconds=base)
        elif job[0] != "google":
            # A slow or paused Google sweep must not delay other publishers.
            # Saved attempt times keep their cadence stable across restarts.
            due = now if manual or not attempted else next_refresh(attempted, self.interval)
        elif new_cycle or not attempted_this_round:
            due = now
        else:
            due = self.next_refresh_at or now
            if not self.cycle_finished_at and due <= now:
                # A deliberately slow Google sweep may outlast the interval.
                # Finish it before downloading already-completed feeds again.
                due = datetime.max.replace(tzinfo=UTC)
        if job[0] == "google" and self.google_until and self.google_until > due:
            due = self.google_until
        return due

    def _schedule(self):
        while True:
            self.scan_requested.clear()
            delay = 60
            try:
                close_old_connections()
                with self.condition:
                    reload_config, self.reload_requested = self.reload_requested, False
                if reload_config:
                    self._load_configuration()
                self._finish_cycle()
                now = datetime.now(UTC)
                with self.condition:
                    manual = self.force_requested
                    due = self.next_refresh_at is None or now >= self.next_refresh_at and self.cycle_finished_at is not None
                if manual or due:
                    self._begin_cycle(now, manual)
                with self.condition:
                    deadlines = [self.next_refresh_at]
                    for job in self.jobs:
                        if job in self.running or job in self.normal or job in self.urgent:
                            continue
                        deadline = self._due_at(job, now)
                        if deadline <= now:
                            self._enqueue(job, urgent=job[0] != "google", force=True)
                        else:
                            deadlines.append(deadline)
                self._finish_cycle()
                with self.condition:
                    cleanup, full = self.maintenance_requested, self.full_cleanup
                    self.maintenance_requested = self.full_cleanup = False
                if cleanup:
                    maintain_archive(force=full)
                future = [deadline for deadline in deadlines if deadline is not None and deadline > now]
                with self.condition:
                    self.wake_at = min(future) if future else None
                delay = min(settings.NEWS_SCHEDULER_MAX_SLEEP_SECONDS, max(1, (self.wake_at - datetime.now(UTC)).total_seconds())) if self.wake_at else settings.NEWS_SCHEDULER_MAX_SLEEP_SECONDS
            except Exception:
                with self.condition:
                    self.reload_requested = True
                logger.exception("Background feed scheduling failed; will retry")
            finally:
                close_old_connections()
            self.scan_requested.wait(delay)

    def _next_job(self, priority_only):
        google_running = any(job[0] == "google" for job in self.running)
        queues = (self.urgent,) if priority_only else (self.urgent, self.normal)
        for queue in queues:
            for job in queue:
                # Only one worker needs Google's serialized request slot.
                # Leave the other workers available for independent feeds.
                if job[0] != "google" or not google_running:
                    return queue, job
        return None

    def _worker(self, priority_only):
        while True:
            with self.condition:
                queue, job = self.condition.wait_for(lambda: self.ready and self._next_job(priority_only))
                retry = queue.pop(job)
                self.running.add(job)
                force = job in self.force_jobs
                self.force_jobs.discard(job)
            try:
                close_old_connections()
                self._run(job, retry, force)
            except ArchiveWriteError:
                self._archive_failed(job)
            except Exception:
                logger.exception("Background feed %s failed", job)
                self._unexpected_failure(job)
            finally:
                close_old_connections()
                with self.condition:
                    self.running.discard(job)
                    if not (self.urgent or self.normal or self.running):
                        self.maintenance_requested = True
                    self.condition.notify_all()
                self.scan_requested.set()

    def _run(self, job, retry, force=False):
        with self.condition:
            registry, interval = self.registry, self.interval
            if job not in self.jobs:
                return None
            key = self.jobs[job]
            archive_pending = self.states.get(key, {}).get("metadata", {}).get("archive_pending")
        if archive_pending:
            with cache_lock(key):
                snapshot = cache.get(key)
                if isinstance(snapshot, dict) and snapshot.get("last_success_at"):
                    if not capture_snapshot(job, snapshot, registry):
                        raise ArchiveWriteError()
                    state = FeedState.objects.get(pk=key)
                    metadata = snapshot_metadata(snapshot)
                    metadata["saved_at"] = state.metadata.get("saved_at") or metadata.get("last_attempt_at")
                    with database_write():
                        FeedState.objects.filter(pk=key).update(metadata=metadata)
                    state.metadata = metadata
                    self.snapshot_saved(state)
                    return True
        kind, identity = job
        options = {"fresh_seconds": interval, "retry_failed": retry, "force_refresh": force}
        if kind == "rss":
            feed = next((feed for feed in registry.feeds if feed.id == identity), None)
            result = get_fixed_feed(feed, registry.get_provider(feed.provider_id), **options)
            success = not result.refresh_failed
            key = fixed_feed_cache_key(feed)
        elif kind == "youtube":
            source = registry.get(identity)
            result = get_youtube_feed(source, **options)
            success = not result.refresh_failed
            key = youtube_cache_key(source)
        else:
            if google_pause_until(cache, datetime.now(UTC)):
                return None
            result = get_world_news(registry=registry, **options) if identity == "WORLD" else get_country_news(identity, registry=registry, **options)
            success = not (result.error or result.warning)
            key = google_cache_key(registry.get("google_news_country"), identity)
        if success:
            if not capture_snapshot(job, cache.get(key), registry):
                raise ArchiveWriteError()
            with self.condition:
                if key in self.states:
                    self.states[key]["archive_stamp"] = self.states[key]["metadata"].get("last_success_at", "")
        return success

    def _archive_failed(self, job):
        with self.condition:
            key = self.jobs.get(job)
            if key is None:
                return
            state = self.states.setdefault(key, {})
            metadata = {**state.get("metadata", {}), "archive_pending": True,
                        "last_error": "Downloaded news could not be added to retained coverage.",
                        "last_error_detail": "",
                        "retry_after_at": (datetime.now(UTC) + timedelta(seconds=(settings.NEWS_GOOGLE_FAILURE_BACKOFF_SECONDS
                            if job[0] == "google" else settings.NEWS_FAILURE_BACKOFF_SECONDS))).isoformat()}
            metadata.pop("retry_requested_at", None)
            state["metadata"] = metadata
        try:
            with database_write():
                FeedState.objects.filter(pk=key).update(metadata=metadata)
        except DatabaseError:
            # The durable archive checkpoint still identifies the unfinished
            # import if the database is also unavailable for this status write.
            logger.warning("Could not retain the archive retry time for %s", job)

    def _unexpected_failure(self, job):
        now = datetime.now(UTC)
        with self.condition:
            key = self.jobs.get(job)
            if key is None:
                return
            state = self.states.setdefault(key, {})
            metadata = {**state.get("metadata", {}), "last_error": "The last check could not be completed.",
                        "last_error_detail": "", "last_attempt_at": now.isoformat(), "saved_at": now.isoformat()}
            metadata.pop("retry_requested_at", None)
            record_failure(metadata, now, RuntimeError(), google=job[0] == "google")
            state["metadata"] = metadata
            expiry = state.get("expires_at") or now + timedelta(seconds=settings.NEWS_STALE_SECONDS)
        try:
            with write_transaction():
                FeedState.objects.update_or_create(pk=key, defaults={"metadata": metadata, "expires_at": expiry})
        except DatabaseError:
            logger.warning("Could not retain the retry time for %s", job)


feed_warmer = FeedWarmer()
