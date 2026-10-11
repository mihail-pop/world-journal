# News-source settings

Open **Settings → Manage news sources** (`/settings/news/`). Preferences are
shared by this local installation and stored in SQLite. No accounts or new
dependencies are required.

## Choices and freshness

- Google News, regional publishers, their individual feeds, and YouTube channels
  have separate on/off choices. Save the form to apply changes.
- Switching off a publisher pauses its feeds without forgetting their individual
  choices. Re-enabling it restores those choices.
- Unavailable records in the curated registry stay locked. In particular, the
  four previously failed YouTube candidate IDs cannot be enabled here.
- Successful cache entries are reused for 5–120 minutes (15 by default). This is
  a freshness threshold, not a background timer: requests trigger refreshes.
- Changing preferences does not remove cached feeds, journal items, or the playing
  video. Already displayed drawer results remain until a new request is made.

The registry remains authoritative for endpoint URLs, channel identity, routing,
language, and audit metadata. The preferences can disable reviewed records, but
cannot enable an unavailable registry record. Disabled records are skipped before
fetching. Videos remain lazy on the Map page.

## Health and manual refresh

Opening this page reads the retained feed cache; it does not contact publishers.
Google News health is specific to the selected country. Regional and YouTube
health covers the whole feed, so its entry count can differ from country matches.

**Refresh now** checks one saved, enabled endpoint. It bypasses normal freshness
and failure backoff for that request, but keeps existing bounded fetching,
conditional requests, identity validation, and stale fallback. A successful empty
feed is different from a failed refresh. Save checkbox edits before refreshing or
changing the country selector, as those actions reload the page.

The last successful check includes HTTP 304 responses. Registry review dates are
separate historical audit dates. Health is not a permanent event log: when the
underlying cache expires, the page reports no retained check. A failed refresh
retains prior usable results where available.

## Setup and manual checks

Use the workspace virtual environment:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000/` and reload with Ctrl+F5 after updating static files.

1. Open source settings. Sources and saved choices appear without a bulk feed
   refresh. Initially, some sources may have no retained check.
2. Turn Google News off and save. Open a country's Articles tab: Google shows a
   switched-off message while enabled regional coverage remains available.
3. Disable a regional publisher and save, then enable it again. Its individual
   feed checkbox choices should be retained. Unavailable channels remain locked.
4. Save a freshness value, revisit the page, and confirm it persists. Values
   outside 5–120 should show a validation message.
5. Refresh one enabled source. Its attempt time and cache status update; a remote
   failure shows a warning and keeps prior usable cached entries. Google checks
   use the chosen country.
6. Try the page in all themes and a narrow window. Navigate between Map, Journal,
   and Settings while a video plays; the shell player should stay intact.

Automated tests and browser acceptance were intentionally left to the user for
this implementation step.
