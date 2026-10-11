"""Bounded, process-local feed refresh for the single-server local installation.

Starts on the first page request, never in AppConfig.ready or management commands.
Daemon threads stop with Django; retained SQLite snapshots survive restarts.
"""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from datetime import UTC, datetime
from threading import Condition, Event, Lock, Thread

from django.conf import settings
from django.core.cache import cache
from django.db import close_old_connections

from news.preferences import effective_registry, freshness_seconds
from news.types import SourceKind

from .cache import age, fixed_feed_cache_key, google_cache_key, youtube_cache_key
from .country_news import _countries_by_code, _country_for_code, get_country_news
from .regional_news import get_fixed_feed
from .region_routing import eligible_youtube_sources
from .youtube_news import get_youtube_feed

logger = logging.getLogger(__name__)


def feed_jobs(registry):
    for feed in registry.feeds:
        if feed.enabled_by_default:
            yield ("rss", feed.id), fixed_feed_cache_key(feed)
    for source in registry.sources:
        if source.enabled_by_default and source.kind is SourceKind.YOUTUBE:
            yield ("youtube", source.id), youtube_cache_key(source)
    google = registry.get("google_news_country")
    if google.enabled_by_default:
        for code in _countries_by_code():
            yield ("google", code), google_cache_key(google, code)


def needs_refresh(snapshot, interval, now):
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("items"), list):
        return True
    if snapshot.get("last_error"):
        attempted_age = age(now, snapshot.get("last_attempt_at"))
        # Background failures retry gently; clicking Retry remains immediate.
        return attempted_age is None or attempted_age.total_seconds() >= min(interval, 300)
    fetched_age = age(now, snapshot.get("fetched_at"))
    return not snapshot.get("last_success_at") or fetched_age is None or fetched_age.total_seconds() >= interval


class FeedWarmer:
    def __init__(self):
        self.condition = Condition()
        self.started = False
        self.urgent = OrderedDict()
        self.normal = OrderedDict()
        self.running = set()
        self.google_pacing = Lock()
        self.next_google_at = 0.0
        self.scan_requested = Event()

    def start(self):
        with self.condition:
            if self.started:
                return
            self.started = True
            # One reserved lane keeps a clicked country ahead of a world-wide scan.
            for index in range(settings.NEWS_BACKGROUND_WORKERS):
                Thread(target=self._worker, args=(False,), daemon=True, name=f"feeds-{index}").start()
            Thread(target=self._worker, args=(True,), daemon=True, name="feeds-priority").start()
            Thread(target=self._schedule, daemon=True, name="feeds-refresh").start()

    def _enqueue(self, job, *, urgent=False, retry=False):
        with self.condition:
            if job in self.running:
                return
            if urgent:
                previous_retry = self.normal.pop(job, False) or self.urgent.get(job, False)
                retry = retry or previous_retry
                self.urgent[job] = retry
                self.urgent.move_to_end(job, last=False)
            elif job not in self.urgent and job not in self.normal:
                self.normal[job] = retry
            self.condition.notify_all()

    def prioritize(self, code, *, retry=False):
        country = _country_for_code(code)
        self.start()
        registry, interval = effective_registry(), freshness_seconds()
        jobs = [(job, key) for job, key in feed_jobs(registry) if job[0] == "rss" or job == ("google", country["iso_a2"])]
        jobs += [(("youtube", source.id), youtube_cache_key(source)) for source in eligible_youtube_sources(country, registry)]
        snapshots = cache.get_many([key for _, key in jobs])
        now = datetime.now(UTC)
        # Enqueue shared feeds first, then Google last so the newest country goes first.
        jobs.sort(key=lambda pair: pair[0][0] == "google")
        for job, key in jobs:
            snapshot = snapshots.get(key)
            if needs_refresh(snapshot, interval, now) or retry and isinstance(snapshot, dict) and snapshot.get("last_error"):
                self._enqueue(job, urgent=True, retry=retry)

    def busy(self):
        with self.condition:
            return bool(self.urgent or self.normal or self.running)

    def rescan(self):
        self.start()
        self.scan_requested.set()

    def _schedule(self):
        while True:
            self.scan_requested.clear()
            try:
                close_old_connections()
                registry, interval = effective_registry(), freshness_seconds()
                jobs = tuple(feed_jobs(registry))
                snapshots = cache.get_many([key for _, key in jobs])
                now = datetime.now(UTC)
                for job, key in jobs:
                    if needs_refresh(snapshots.get(key), interval, now):
                        self._enqueue(job)
            except Exception:
                logger.exception("Background feed scheduling failed; will retry")
            finally:
                close_old_connections()
            self.scan_requested.wait(settings.NEWS_BACKGROUND_SCAN_SECONDS)

    def _worker(self, priority_only):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: bool(self.urgent) or not priority_only and bool(self.normal))
                queue = self.urgent if self.urgent else self.normal
                job, retry = queue.popitem(last=False)
                self.running.add(job)
            try:
                close_old_connections()
                self._run(job, retry)
            except Exception:
                logger.exception("Background feed %s failed", job)
            finally:
                close_old_connections()
                with self.condition:
                    self.running.discard(job)

    def _run(self, job, retry):
        # Re-read switches at dispatch: disabling a queued feed prevents its fetch.
        registry, interval = effective_registry(), freshness_seconds()
        kind, identity = job
        options = {"fresh_seconds": interval, "retry_failed": retry}
        if kind == "rss":
            feed = next((feed for feed in registry.feeds if feed.id == identity), None)
            if feed and feed.enabled_by_default:
                get_fixed_feed(feed, registry.get_provider(feed.provider_id), **options)
        elif kind == "youtube":
            source = next((source for source in registry.sources if source.id == identity), None)
            if source and source.enabled_by_default:
                get_youtube_feed(source, **options)
        elif registry.get("google_news_country").enabled_by_default:
            # Smooth out the initial 238-country sweep instead of flooding Google.
            with self.google_pacing:
                delay = self.next_google_at - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                self.next_google_at = time.monotonic() + settings.NEWS_GOOGLE_REQUEST_SPACING_SECONDS
            get_country_news(identity, registry=registry, **options)


feed_warmer = FeedWarmer()
