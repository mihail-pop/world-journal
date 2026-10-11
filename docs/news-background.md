# Background news cache

Opening any application page starts a small feed queue inside the running Django
process. No separate worker, scheduler, new dependency or browser automation is
required. Two workers prepare feeds; a third lane handles selected countries.
This is intended for the project's single-process local server.

## Preparation and refresh

- All enabled regional RSS feeds and YouTube channel feeds are prepared first.
- Google News has one generated feed per country, not one complete world feed.
  All 238 countries are queued; requests start at least 0.75 seconds apart.
- Selecting a country promotes its Google request and missing/shared feeds.
  A request already fetching cannot be interrupted, but duplicate jobs are avoided.
- A scan every 30 seconds queues feeds whose own successful-check timestamp is
  older than the saved refresh interval (30 minutes by default).
- Failed feeds retain usable stale data. Automatic retries wait five minutes;
  explicit Retry and source Refresh now can bypass that backoff.
- Switches are rechecked when a job starts, so a disabled queued source is skipped.
  Saving source preferences also wakes the scheduler.

The queue continues after browser tabs close, while the Django process runs.
Stopping the server stops all fetching. After a restart, opening a page resumes
preparation from retained SQLite snapshots. Development autoreloads restart the
queue similarly. Management commands do not start it.

Al Arabiya's provider and five feed records have been removed. The migration
removes their obsolete source choices and changes a saved legacy 15-minute
interval to 30; other saved intervals and journal entries are retained. Old feed
cache records expire normally.

## Immediate drawer display

Country endpoints read cached snapshots only: no publisher requests and no waits
on a feed lock. Available articles appear while missing feeds are prepared, with
an honest preparation message instead of a false empty/failure state.

The browser prepares country HTML in batches of at most 20 and retains it across
country selections and page navigation. A repeated selection uses that HTML
immediately. A first selection can also be immediate once its background batch
has arrived. Unchanged batch versions return no repeated HTML. The browser checks
every five seconds during preparation and every 30 seconds afterward; hidden tabs
pause their UI polling, while server fetching continues. New content updates an
open drawer without a full-page reload or clearing its current article filter.

Only HTML strings are stored for unopened video drawers, so preloading does not
fetch thumbnails or create iframes. Play still creates the validated persistent
player. Country identities, request ordering and source-change generations prevent
late responses from replacing another country's drawer or restoring old choices.
Country matching and duplicate identification are reused to keep the world-wide
HTML preparation from repeating the same work.

The initial Google sweep takes at least about three minutes at the configured
pacing, possibly longer with slow or failing feeds. Selected countries do not
wait for that sweep to finish. Warm cached content is immediate in the browser;
new data still depends on publisher availability. Refresh does not replace useful
old content with a loading screen.

## Manual checks

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Reload the app with Ctrl+F5 after updating JavaScript.

1. Confirm Al Arabiya is absent from Sources. Confirm a 30-minute interval, unless
   a different nondefault interval was previously saved.
2. Open a country during initial preparation: existing cached articles should
   show immediately; remaining results should appear automatically.
3. Switch between countries, close/reopen the drawer, and use back/forward. Warm
   results should appear immediately and never switch to another country's data.
4. Open Videos, switch countries and return. Cached videos should appear without
   another publisher wait; no player appears until Play. Navigation and feed
   updates must preserve the playing iframe.
5. Navigate to Journal/Settings and back. The map, viewport and drawer remain.
6. Disable a source and save. Cached drawer results should update to exclude it;
   other sources and journal entries remain intact.
7. Temporarily select a five-minute refresh interval, leave the server running
   and close the browser. Reopen after six minutes and check source timestamps.
   They should have advanced without country clicks. Restore 30 afterward.
8. If offline or a publisher fails, retained articles should remain visible.
   A never-successful feed should show a source failure rather than fabricated data.

No test suite, new tests, live feed sweep or browser acceptance was run for this
implementation. Verification is left to the user.
