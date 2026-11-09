from time import sleep

from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.db import DatabaseCache
from django.db import DatabaseError, OperationalError

from core.database import database_write, is_database_busy


class CacheWriteError(DatabaseError):
    pass


class FeedDatabaseCache(DatabaseCache):
    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        key = self.make_and_validate_key(key, version=version)
        for delay in (0, 0.1):
            if delay:
                sleep(delay)
            try:
                # DatabaseCache.set discards the write result. Retry the same
                # snapshot so transient contention doesn't require another fetch.
                with database_write():
                    if self._base_set("set", key, value, timeout):
                        return
            except OperationalError as error:
                if not is_database_busy(error):
                    raise
        raise CacheWriteError("Could not save the news cache after retrying.")
