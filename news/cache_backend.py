from datetime import UTC, datetime
from time import sleep

from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.db import DatabaseCache
from django.db import DatabaseError, OperationalError

from core.database import database_write, is_database_busy, write_transaction
from .feed_state import is_feed_key, snapshot_metadata
from .models import FeedState


class CacheWriteError(DatabaseError):
    pass


class FeedDatabaseCache(DatabaseCache):
    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        feed_key = key if is_feed_key(key) and isinstance(value, dict) else None
        key = self.make_and_validate_key(key, version=version)
        for delay in (0, 0.1):
            if delay:
                sleep(delay)
            try:
                # DatabaseCache.set discards the write result. Retry the same
                # snapshot so transient contention doesn't require another fetch.
                with write_transaction():
                    if self._base_set("set", key, value, timeout):
                        if feed_key:
                            deadline = self.get_backend_timeout(timeout)
                            expires = datetime.fromtimestamp(deadline, UTC) if deadline is not None else datetime.max.replace(tzinfo=UTC)
                            state = FeedState(cache_key=feed_key, metadata=snapshot_metadata(value), expires_at=expires)
                            FeedState.objects.bulk_create([state], update_conflicts=True,
                                unique_fields=["cache_key"], update_fields=["metadata", "expires_at"])
                        break
            except OperationalError as error:
                if not is_database_busy(error):
                    raise
        else:
            raise CacheWriteError("Could not save the news cache after retrying.")
        if feed_key:
            from .services.background import feed_warmer
            feed_warmer.snapshot_saved(state)
        elif key.endswith(":news:google_rate_limit"):
            from .services.background import feed_warmer
            feed_warmer.google_cooldown(value)

    def _base_delete_many(self, keys):
        # Django also calls this from get/get_many when a record has expired.
        if not keys:
            return False
        with database_write():
            return super()._base_delete_many(keys)
