"""Persisted refresh rounds, sleeping workers, and status from saved feed state."""
from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from threading import Condition, Event, Lock, Thread
from unicodedata import combining, normalize

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, close_old_connections
from django.utils.timezone import localtime

from core.database import database_write, write_transaction
from countries.models import Country
from news.feed_state import snapshot_metadata
from news.google_pacing import gap_label, maximum_gap
from news.models import FeedSchedule, FeedState
from news.preferences import effective_registry, refresh_preferences
from news.types import SourceKind

from .archive import capture_snapshot, maintain_archive
from .cache import (
    GOOGLE_COOLDOWN_KEY, cache_lock, failure_deadline, fixed_feed_cache_key, google_cache_key,
    google_pause_until, google_request_spacing_range, next_refresh, parse_datetime, record_failure, youtube_cache_key,
)
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


def ranked_google_codes(codes):
    ranks = {}
    for code, name, count in Country.objects.order_by().values_list("code", "name", "selection_count__count"):
        alphabetical = "".join(char for char in normalize("NFD", name.casefold()) if not combining(char))
        ranks[code] = (-(count or 0), alphabetical, code)
    ranked = sorted((code for code in codes if code != "WORLD"), key=lambda code: ranks.get(code, (0, code.casefold(), code)))
    return (["WORLD"] if "WORLD" in codes else []) + ranked


def source_problem(job, metadata, paused_country=None):
    if not metadata.get("last_error"):
        return None
    message = metadata.get("last_error_detail") or metadata["last_error"]
    if job[0] == "google" and "HTTP 429" in message and job[1] != paused_country:
        return None
    return message


class FeedWarmer:
    def __init__(self):
        self.condition = Condition()
        self.refresh_lock = Lock()
        self.started = self.ready = False
        self.registry = None
        self.interval = settings.NEWS_REFRESH_SECONDS
        self.jobs, self.states = {}, {}
        self.refresh_started_at = self.next_refresh_at = self.google_until = None
        self.google_state, self.google_pacing = {}, {}
        self.google_resume = None
        self.google_ready_at = None
        self.google_sweep_started_at = None
        self.google_sweep_order = []
        self.wake_at = None
        self.reload_requested = True
        self.force_requested = False
        self.maintenance_requested = self.full_cleanup = False
        self.urgent, self.normal = OrderedDict(), OrderedDict()
        self.running, self.force_jobs = set(), set()
        self.scan_requested = Event()
        self.cycle_finished_at = None
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
            deadline = parse_datetime(state.metadata.get("google_request_ready_at"))
            if deadline and (self.google_ready_at is None or deadline > self.google_ready_at):
                self.google_ready_at = deadline
        self.scan_requested.set()

    def google_cooldown(self, snapshot):
        with self.condition:
            new_limit = snapshot.get("last_rate_limit_at") != self.google_state.get("last_rate_limit_at")
            self.google_state = snapshot
            self.google_until = parse_datetime(snapshot.get("retry_after_at"))
            if snapshot.get("resume_country"):
                self.google_resume = snapshot["resume_country"]
            if new_limit:
                for queue in (self.urgent, self.normal):
                    for job in tuple(queue):
                        if job[0] == "google":
                            queue.pop(job)
                            self.force_jobs.discard(job)
                self.condition.notify_all()
        self.scan_requested.set()

    def _google_sweep_jobs(self):
        return [("google", code) for code in self.google_sweep_order if ("google", code) in self.jobs]

    def _google_checked(self, job):
        metadata = self.states.get(self.jobs[job], {}).get("metadata", {})
        attempted = parse_datetime(metadata.get("last_attempt_at"))
        if not attempted or not self.google_sweep_started_at or attempted < self.google_sweep_started_at:
            return False
        blocked = parse_datetime(self.google_state.get("last_rate_limit_at")) if job[1] == self.google_resume else None
        return (not blocked or attempted > blocked) and "HTTP 429" not in (metadata.get("last_error_detail") or "")

    def _next_google_job(self):
        return next((job for job in self._google_sweep_jobs() if not self._google_checked(job)), None)

    def _start_google_sweep(self, now):
        with self.refresh_lock:
            with self.condition:
                if self._next_google_job() or any(job[0] == "google" for job in (*self.running, *self.normal)):
                    return
                jobs = [job for job in self.jobs if job[0] == "google"]
                if not any(self._due_at(job, now) <= now for job in jobs):
                    return
                codes = [job[1] for job in jobs]
                started = now
                legacy_pause = None
                if self.google_sweep_started_at is None and not self.manual_refresh:
                    resume = ("google", self.google_resume)
                    metadata = self.states.get(self.jobs.get(resume), {}).get("metadata", {})
                    if "HTTP 429" in (metadata.get("last_error_detail") or ""):
                        legacy_pause = parse_datetime(self.google_state.get("last_rate_limit_at"))
                    # Reuse recent check timestamps during the first sweep after an upgrade.
                    started = (legacy_pause or now) - timedelta(seconds=settings.NEWS_GOOGLE_REFRESH_SECONDS)
            if legacy_pause and self.google_resume in codes:
                index = codes.index(self.google_resume)
                order = codes[index:] + codes[:index]
            else:
                order = ranked_google_codes(codes)
            with database_write():
                FeedSchedule.objects.filter(pk=1).update(google_sweep_started_at=started, google_sweep_order=order)
            with self.condition:
                self.google_sweep_started_at, self.google_sweep_order = started, order
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

    def _promote(self, jobs):
        # Opening a page only changes the order of work already scheduled.
        with self.condition:
            for job in jobs:
                if job in self.normal or job in self.urgent:
                    self._enqueue(job, urgent=True)

    def prioritize(self, code):
        country = _country_for_code(code)
        self.start()
        with self.condition:
            if self.registry is None:
                return
            jobs = [job for job in self.jobs if job[0] == "rss"]
            jobs += [("youtube", source.id) for source in eligible_youtube_sources(country, self.registry)]
            self._promote(jobs)

    def prioritize_news(self, *, country="WORLD", videos=False):
        self.start()
        with self.condition:
            self._promote([job for job in self.jobs if (
                videos and job[0] == "youtube"
                or not videos and job[0] == "rss"
            )])

    def request_google(self, code):
        self.start()
        with self.refresh_lock, self.condition:
            job = ("google", code)
            if job not in self.jobs or self.google_until and self.google_until > datetime.now(UTC):
                return False
            next_job = self._next_google_job()
            if next_job is not None and next_job != job:
                return job in self._google_sweep_jobs() and not self._google_checked(job)
            self._enqueue(job, force=True)
        self.scan_requested.set()
        return True

    def busy(self):
        with self.condition:
            return not self.ready or self.force_requested or bool(self.urgent or self.normal or self.running)

    def sources_need_attention(self):
        with self.condition:
            if ("google", "WORLD") in self.jobs and self.google_until and self.google_until > datetime.now(UTC):
                return True
            return any(source_problem(job, self.states.get(key, {}).get("metadata", {})) for job, key in self.jobs.items())

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
                else:
                    schedule.manual_requested = True
                    schedule.save(update_fields=["manual_requested"])
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
        if job in self.running:
            return "running"
        if job in self.normal or job in self.urgent:
            return "queued"
        state = self.states.get(self.jobs[job], {})
        metadata = state.get("metadata", {})
        attempted = parse_datetime(metadata.get("last_attempt_at"))
        fresh_at_start = (attempted and self.refresh_started_at and not self.manual_refresh
                          and next_refresh(attempted, self._interval_for(job)) > self.refresh_started_at)
        if self.refresh_started_at and attempted and (attempted >= self.refresh_started_at or fresh_at_start) and not metadata.get("archive_pending"):
            if metadata.get("last_error"):
                return "failed"
            if metadata.get("last_success_at") == state.get("archive_stamp"):
                return "done"
        return "waiting"

    def progress(self):
        with self.condition:
            active = set(self.running) | self.normal.keys() | self.urgent.keys()
            phase = next((kind for kind in ("rss", "youtube", "google") if any(job[0] == kind for job in active)), None)
            if phase == "google" and self.google_sweep_order:
                countries = [job for job in self._google_sweep_jobs() if job[1] != "WORLD"]
                total = len(countries)
                completed = sum(self._google_checked(job) for job in countries)
            else:
                scoped = [self._progress_state(job) for job in self.jobs if job[0] == phase and job != ("google", "WORLD")]
                total = len(scoped)
                completed = sum(state in {"done", "failed"} for state in scoped)
            return {
                "phase": phase,
                "total": total,
                "completed": completed,
                "busy": self.busy(), "running": [job for job in self.jobs if job in self.running and job[0] == phase],
                "finished_at": self.cycle_finished_at,
            }

    def pacing_status(self, preferences=None):
        with self.condition:
            pacing = self.google_pacing if preferences is None else preferences
            state = self.google_state
            history = state.get("gap_history", {})
            today = localtime().date()
            dates = {today.isoformat(), (today - timedelta(days=1)).isoformat()}
            if not dates.issubset(history):
                recent = {}
                for key, entry in self.states.items():
                    if ":google_country:" not in key:
                        continue
                    metadata = entry["metadata"]
                    stamp = parse_datetime(metadata.get("last_attempt_at"))
                    low = metadata.get("google_spacing_seconds")
                    if not stamp or low is None:
                        continue
                    day = localtime(stamp).date().isoformat()
                    if day in dates and (day not in recent or stamp > recent[day][0]):
                        recent[day] = (stamp, (low, metadata.get("google_spacing_max_seconds") or low + 5))
                history = {**{day: value[1] for day, value in recent.items()}, **history}
            return {
                "current": gap_label(google_request_spacing_range(state, pacing)),
                "today": gap_label(history.get(today.isoformat())),
                "yesterday": gap_label(history.get((today - timedelta(days=1)).isoformat())),
                "maximum": gap_label(maximum_gap(pacing)),
                "fixed": gap_label(pacing.get("fixed")),
                "custom_maximum": gap_label(pacing.get("maximum")),
            }

    def status(self):
        """No SQL, even while the Sources page is watching an active refresh."""
        with self.condition:
            progress = self.progress()
            registry, jobs, states, paused = self.registry, dict(self.jobs), dict(self.states), self.google_until
            resume = self.google_resume
            now = datetime.now(UTC)
            active = set(self.running) | self.normal.keys() | self.urgent.keys()
            due_times = {job: self._due_at(job, now) for job in self.jobs}
            google_next = self._next_google_job()
            deadlines = [deadline for job, deadline in due_times.items()
                         if job not in active and (job[0] != "google" or google_next is None or job == google_next)]
            if self.next_refresh_at and self.cycle_finished_at and self.next_refresh_at > now:
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
        problems = OrderedDict()

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
            if message := source_problem(job, metadata, resume if google_paused else None):
                add_problem(job, message)
        errors = []
        for group in problems.values():
            messages = [group["pause"]] if group["pause"] else []
            for message, scopes in group["messages"].items():
                scope = ", ".join(scopes[:5])
                if len(scopes) > 5:
                    scope += f" and {len(scopes) - 5} more"
                if group["pause"] and "HTTP 429" in message:
                    messages.append(f"Rate-limited check: {scope}.")
                else:
                    messages.append(f"{scope + ': ' if scope else ''}{message.rstrip('. ')}.")
            retrying = not group["pause"] and (bool(active.intersection(group["jobs"])) or any(
                states.get(jobs[job], {}).get("metadata", {}).get("retry_requested_at") for job in group["jobs"]
            ))
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
        return {**progress, "errors": errors, "failed": len(errors), "enabled": len(jobs), "missing": missing,
                "next_update_at": next_update.isoformat() if next_update else None, "google_pacing": self.pacing_status()}

    def _load_configuration(self):
        registry = effective_registry()
        interval, pacing = refresh_preferences()
        jobs = dict(feed_jobs(registry))
        states = {row.cache_key: {"metadata": row.metadata, "expires_at": row.expires_at, "archive_stamp": row.archive_stamp}
                  for row in FeedState.objects.filter(cache_key__in=jobs.values())}
        schedule = FeedSchedule.objects.filter(pk=1).first()
        if schedule and schedule.next_refresh_at != next_refresh(schedule.cycle_started_at, interval):
            schedule.next_refresh_at = next_refresh(schedule.cycle_started_at, interval)
            with write_transaction():
                schedule.save(update_fields=["next_refresh_at"])
        with self.condition:
            self.registry, self.interval, self.jobs = registry, interval, jobs
            self.google_pacing = pacing
            self.google_state = cache.get(GOOGLE_COOLDOWN_KEY) or {}
            self.google_until = parse_datetime(self.google_state.get("retry_after_at"))
            self.google_resume = self.google_state.get("resume_country")
            for key, state in states.items():
                previous = self.states.get(key, {}).get("metadata", {})
                previous_saved = parse_datetime(previous.get("saved_at")) or parse_datetime(previous.get("last_attempt_at"))
                loaded_saved = parse_datetime(state["metadata"].get("saved_at")) or parse_datetime(state["metadata"].get("last_attempt_at"))
                if not previous_saved or loaded_saved and loaded_saved >= previous_saved:
                    self.states[key] = state
            google_metadata = [(job, self.states.get(key, {}).get("metadata", {}))
                               for job, key in jobs.items() if job[0] == "google"]
            deadlines = [parse_datetime(metadata.get("google_request_ready_at")) for _job, metadata in google_metadata]
            self.google_ready_at = max((value for value in (self.google_ready_at, *deadlines) if value), default=None)
            if not self.google_resume and self.google_state.get("last_rate_limit_at"):
                rate_limited = [(metadata.get("last_attempt_at") or "", job[1]) for job, metadata in google_metadata
                                if "HTTP 429" in (metadata.get("last_error_detail") or "")]
                if rate_limited:
                    attempted_at, country = max(rate_limited)
                    attempted = parse_datetime(attempted_at)
                    blocked = parse_datetime(self.google_state["last_rate_limit_at"])
                    if attempted and blocked and timedelta() <= blocked - attempted <= timedelta(seconds=settings.NEWS_HTTP_TOTAL_TIMEOUT_SECONDS):
                        self.google_resume = country
            if schedule:
                self.refresh_started_at, self.next_refresh_at = schedule.cycle_started_at, schedule.next_refresh_at
                self.cycle_finished_at = schedule.cycle_finished_at.isoformat() if schedule.cycle_finished_at else None
                self.manual_refresh = schedule.cycle_manual
                self.force_requested |= schedule.manual_requested
                self.google_sweep_started_at = schedule.google_sweep_started_at
                self.google_sweep_order = schedule.google_sweep_order
            self.urgent = OrderedDict((job, retry) for job, retry in self.urgent.items() if job in jobs)
            self.normal = OrderedDict((job, retry) for job, retry in self.normal.items() if job in jobs)
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
                self.cycle_finished_at = None
                self.manual_refresh = manual
                self.force_requested = False

    def _finish_cycle(self):
        with self.refresh_lock:
            with self.condition:
                if not self.refresh_started_at or self.cycle_finished_at or self.running or self.normal or self.urgent:
                    return
                started = self.refresh_started_at
            finished = datetime.now(UTC)
            with database_write():
                saved = FeedSchedule.objects.filter(pk=1, cycle_started_at=started).update(cycle_finished_at=finished)
            with self.condition:
                if saved and self.refresh_started_at == started:
                    self.cycle_finished_at = finished.isoformat()
                    self.maintenance_requested = self.full_cleanup = True

    def _interval_for(self, job):
        return settings.NEWS_GOOGLE_REFRESH_SECONDS if job[0] == "google" else self.interval

    def _due_at(self, job, now):
        metadata = self.states.get(self.jobs[job], {}).get("metadata", {})
        attempted = parse_datetime(metadata.get("last_attempt_at"))
        attempted_this_round = attempted and self.refresh_started_at and attempted >= self.refresh_started_at
        manual = self.manual_refresh and not self.cycle_finished_at and not attempted_this_round
        if metadata.get("archive_pending"):
            due = parse_datetime(metadata.get("retry_after_at")) or now
        elif metadata.get("retry_requested_at") or manual:
            due = now
        elif metadata.get("last_error"):
            due = failure_deadline(metadata, self._interval_for(job)) or now
        else:
            # Each feed keeps its cadence across rounds and server restarts.
            # Slower Google sweeps cannot delay or repeat other publishers.
            due = next_refresh(attempted, self._interval_for(job)) if attempted else now
        publisher_deadline = parse_datetime(metadata.get("server_retry_at"))
        if publisher_deadline and publisher_deadline > due:
            due = publisher_deadline
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
                now = datetime.now(UTC)
                with self.condition:
                    manual = self.force_requested
                    due = self.next_refresh_at is None or now >= self.next_refresh_at and self.cycle_finished_at is not None
                if manual or due:
                    self._begin_cycle(now, manual)
                self._start_google_sweep(now)
                with self.condition:
                    deadlines = [self.next_refresh_at]
                    google_next = self._next_google_job()
                    for job in self.jobs:
                        if job[0] == "google" and google_next is not None and job != google_next:
                            continue
                        if job in self.running or job in self.normal or job in self.urgent:
                            continue
                        deadline = self._due_at(job, now)
                        if deadline <= now and (job[0] != "google" or job == google_next):
                            self._enqueue(job, urgent=job[0] != "google", force=True)
                        else:
                            deadlines.append(deadline)
                    if any(job[0] == "google" for job in self.normal):
                        deadlines.append(self.google_ready_at)
                    self.condition.notify_all()
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
        queues = (self.urgent,) if priority_only else (self.urgent, self.normal)
        for queue in queues:
            for job in queue:
                if job[0] != "google":
                    return queue, job
        if priority_only or self.running:
            return None
        now = datetime.now(UTC)
        if any(deadline and deadline > now for deadline in (self.google_until, self.google_ready_at)):
            return None
        for job in self.normal:
            if job[0] == "google":
                return self.normal, job
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
            registry, interval = self.registry, self._interval_for(job)
            pacing = self.google_pacing
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
            options["pacing"] = pacing
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
                        "retry_after_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}
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
            if job == ("google", self.google_resume) and self.google_until and now < self.google_until:
                return  # The persisted 429 still owns this slot in the sweep.
            state = self.states.setdefault(key, {})
            metadata = {**state.get("metadata", {}), "last_error": "The last check could not be completed.",
                        "last_error_detail": "", "last_attempt_at": now.isoformat(), "saved_at": now.isoformat()}
            metadata.pop("retry_requested_at", None)
            record_failure(metadata, now, RuntimeError(), self._interval_for(job))
            state["metadata"] = metadata
            expiry = state.get("expires_at") or now + timedelta(seconds=settings.NEWS_STALE_SECONDS)
        try:
            with write_transaction():
                FeedState.objects.update_or_create(pk=key, defaults={"metadata": metadata, "expires_at": expiry})
        except DatabaseError:
            logger.warning("Could not retain the retry time for %s", job)


feed_warmer = FeedWarmer()
