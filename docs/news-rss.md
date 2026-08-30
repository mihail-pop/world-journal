# Country news RSS

Phase 3A enables one source family: broad English-language country searches from Google News RSS. Regional RSS and YouTube definitions are represented by the typed registry schema but are not configured or fetched in this phase.

## Provider policy

The active source is declared in `data/news_sources.json`. Google URL construction stays in `news/adapters/google_news.py`; views and browser code never construct or receive a remote feed URL. The global English edition is fixed to `hl=en-US`, `gl=US`, and `ceid=US:en`. These parameters select the Google News edition. They do not claim that an article originates in the selected country.

Searches use the canonical English country name. A short adapter-owned override table adds reviewed aliases or a `country` disambiguator where names commonly collide. Google result links are retained as supplied, including Google redirect links. The application does not scrape article pages, resolve publisher redirects, bypass paywalls, or iframe news sites.

Feed fields are normalized to title, HTTPS link, item-level publisher, UTC publication time, and plain-text feed summary. Templates retain source attribution and escape every field. Exact normalized links and exact title-plus-publisher pairs are deduplicated while provider order is preserved.

## Retrieval boundary

`news/services/fetch.py` accepts URLs only from the application-owned source registry. It requires HTTPS, checks the configured host and standard HTTPS port, rejects non-public DNS results, revalidates every redirect, and caps redirects, bytes, and request time. Conditional `ETag` and `Last-Modified` headers are reused when providers supply them.

The browser requests only `/news/countries/<ISO2>/`. Django validates the code against canonical country data, performs any provider request, and returns escaped HTML. Normal tests use local fixtures and mocked HTTP transports; they never contact Google or a publisher.

## Cache and operation

Normalized snapshots use Django's database cache in the existing SQLite database. Create the cache table once after setup:

```powershell
.venv\Scripts\python.exe manage.py createcachetable
```

Successful snapshots are fresh for 15 minutes and retained for three days. A failed refresh serves the previous snapshot with a visible stale warning. When no successful snapshot exists, the drawer shows a scoped Google News error and retry action. A 60-second failure backoff and a short per-process lock prevent repeated or duplicate refresh attempts.

The relevant settings are `NEWS_REFRESH_SECONDS`, `NEWS_STALE_SECONDS`, `NEWS_FAILURE_BACKOFF_SECONDS`, `NEWS_MAX_ITEMS`, `NEWS_HTTP_*`, and `NEWS_USER_AGENT`. Changing normalization or cache shape requires incrementing `NEWS_CACHE_SCHEMA_VERSION`.