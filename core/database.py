from collections import deque
from contextlib import contextmanager
from sqlite3 import SQLITE_BUSY, SQLITE_LOCKED
from threading import Condition, get_ident

from django.db import connection, transaction


_writers = deque()
_writer_ready = Condition()


@contextmanager
def database_write():
    """Queue application writes in arrival order within this server process."""
    # An outer transaction already owns its SQLite lock. Waiting here could
    # deadlock with a queued writer waiting for that transaction to finish.
    if connection.in_atomic_block:
        yield
        return

    writer = get_ident()
    with _writer_ready:
        nested = bool(_writers and _writers[0] == writer)
        if not nested:
            _writers.append(writer)
    try:
        if not nested:
            with _writer_ready:
                _writer_ready.wait_for(lambda: _writers[0] == writer)
        yield
    finally:
        if not nested:
            with _writer_ready:
                _writers.remove(writer)
                _writer_ready.notify_all()


@contextmanager
def write_transaction():
    with database_write(), transaction.atomic():
        yield


def is_database_busy(error):
    code = getattr(error.__cause__, "sqlite_errorcode", 0)
    return (code & 0xFF) in (SQLITE_BUSY, SQLITE_LOCKED)
