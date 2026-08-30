# Country news and video feeds

Phase 3C combines broad English-language country searches from Google News RSS, deterministic country references from curated regional RSS feeds, and recent country-title matches from trusted YouTube channel Atom feeds. It does not use the YouTube Data API, scrape publisher or channel pages, rank editorial quality, or claim that any source is neutral.

## Registry model

`data/news_sources.json` uses schema 4 with three separate collections:

- `sources` contains dynamic application-owned integrations and independently configured YouTube channels. Google News remains here because its country feed URL is generated per request. YouTube records include a stable source ID, trusted channel ID, canonical channel homepage, language, editorial and coverage regions, strict fetch host, enablement, verification date, audit notes, disabled reason, and presentation priority.
- `providers` contains publisher identity, homepage, language, editorial region, affinity regions, display priority, and provider enablement.
- `feeds` contains an independently enabled RSS endpoint, parent `provider_id`, section label, URL, allowlisted hosts, language, verification date, disabled reason, and operational audit notes.

One provider can own one or more feeds. Feed IDs, provider IDs, and dynamic source IDs are globally unique. Every feed must reference a provider, every provider must own a feed, enabled providers must own at least one enabled feed, enabled feeds cannot belong to disabled providers, and active feed URLs cannot collide. All configured URLs must use HTTPS. An enabled feed requires complete audit metadata; a disabled feed requires an exact reason.

Views and browser code never construct or receive remote feed URLs. Google URL construction remains in `news/adapters/google_news.py` with the fixed global English edition `hl=en-US`, `gl=US`, and `ceid=US:en`. Those parameters select the Google edition; they do not establish an article's origin.

YouTube feed URLs are derived from trusted registry channel IDs as `https://www.youtube.com/feeds/videos.xml?channel_id=<CHANNEL_ID>`. Channel IDs are unique and match `UC[A-Za-z0-9_-]{22}`. Enabled records require complete audit metadata, the exact `www.youtube.com/channel/<CHANNEL_ID>` homepage, and only `www.youtube.com` in the feed-host allowlist. Disabled records remain visible in configuration but are never fetched.

## Feed audit

Candidates were checked on 2026-08-30 with one bounded request per supplied URL and one recovery pass after the audit result formatter failed. Requests required HTTPS and public DNS destinations, revalidated redirects, allowed at most three redirects, read at most 512 KiB, and used explicit connect, read, and total timeouts. No publisher page was scraped and no unofficial proxy was substituted.

### Replacement candidates

| Provider / section | Candidate | HTTP / type | Parsed result | Sampled fields | Decision |
| --- | --- | --- | --- | --- | --- |
| Al Arabiya / Top Stories | `https://english.alarabiya.net/feed/rss2/en.xml` | 403, `text/html` | HTML; 0 usable | None | Disabled |
| Al Arabiya / News | `https://english.alarabiya.net/feed/rss2/en/News.xml` | 403, `text/html` | HTML; 0 usable | None | Disabled |
| Al Arabiya / Business | `https://english.alarabiya.net/feed/rss2/en/business.xml` | 403, `text/html` | HTML; 0 usable | None | Disabled |
| Al Arabiya / Energy | `https://english.alarabiya.net/feed/rss2/en/business/energy.xml` | 403, `text/html` | HTML; 0 usable | None | Disabled |
| Al Arabiya / Life | `https://english.alarabiya.net/feed/rss2/en/life-style.xml` | 403, `text/html` | HTML; 0 usable | None | Disabled |
| CGTN / China | `https://www.cgtn.com/subscribe/rss/section/china.xml` | 200, `application/rss+xml` | RSS, title `China`, 50 usable | 20/20 title, link, summary, date; no item publisher | Enabled |
| CGTN / World | `https://www.cgtn.com/subscribe/rss/section/world.xml` | 200, `application/rss+xml` | RSS, title `World`, 49 usable | 20/20 title, link, summary, date; no item publisher | Enabled |
| CGTN / Politics | `https://www.cgtn.com/subscribe/rss/section/politics.xml` | 200, `application/rss+xml` | RSS, title `Politics`, 50 usable | 20/20 title, link, summary, date; no item publisher | Enabled |
| teleSUR / Top Stories | `https://www.telesurenglish.net/feed/` | 200, `application/rss+xml` | RSS, title `teleSUR English`, 30 usable | 20/20 title, link, summary, publisher, date | Enabled |

All final hosts matched their requested hosts and none of these candidates redirected. CGTN World and Politics shared seven exact normalized titles at audit time but no exact normalized URLs. China had no exact title or URL overlap with either sibling. Al Arabiya responses contained no usable items, so their reported zero overlap is not evidence that the sections are distinct.

The old Al Arabiya `https://english.alarabiya.net/feed/default.rss`, CGTN `https://www.cgtn.com/rss/news.xml`, and teleSUR `https://www.telesurenglish.net/rss/news` records are superseded by the candidates above. They are documented here rather than retained as active feed records.

### Existing candidates

The previous bounded audit remains applicable to the other enabled feeds:

| Provider | Result | Decision |
| --- | --- | --- |
| Al Jazeera English | 200 RSS, about 25 usable English items | Enabled |
| CNA | 200 RSS, about 20 usable English items | Enabled |
| NPR | 200 RSS, about 10 usable English items | Enabled |
| CBC News | 200 RSS after same-host path redirect, about 20 usable items | Enabled at `/webfeed/rss/rss-topstories` |
| DW | 200 RSS 1.0/RDF, about 133 usable English items | Enabled |
| France 24 English | 200 RSS, about 24 usable English items | Enabled |
| MercoPress | 200 RSS, about 10 usable English items | Enabled |
| Africanews English | 200 valid RSS, about 50 usable items despite `application/xhtml+xml` | Enabled |
| AllAfrica | 200 valid RSS/RDF, about 32 usable items | Enabled |

Disabled feeds remain in the registry with audit metadata and are never fetched.

### YouTube channel candidates

Each supplied candidate was checked on 2026-08-30 with one bounded request. No candidate needed the one permitted transient retry. Every request used the existing HTTPS, public-address DNS, redirect, timeout, host, and 512 KiB response protections. No channel page was fetched and no replacement ID was searched through an unofficial site.

YouTube's Atom `yt:channelId` value omits the conventional leading `UC`; the five valid feeds consistently returned the remaining 22 characters. Identity validation therefore accepts only the exact trusted registry ID or that ID with exactly its leading `UC` removed. Entries are independently checked against the same identity.

| Channel | Requested ID | HTTP / final host / type | Atom identity and fields | Language | Decision |
| --- | --- | --- | --- | --- | --- |
| Al Jazeera English | `UCNye-wNBqNL5ZzHSJj3l8Bg` | 200 / `www.youtube.com` / `text/xml` | Valid Atom, title/author `Al Jazeera English`, matching `yt:channelId`, 15 usable; 15/15 video ID, title, publication time, watch link, thumbnail | Predominantly English | Enabled |
| CGTN | `UCgrNz-SZj64zgOUV4au9SJA` | 404 / `www.youtube.com` / `text/html` | Not Atom; no returned identity or entries | Not assessable | Disabled: candidate feed returned 404 |
| CNA | `UC83jt4dlz1Gjl58fzQrrkkA` | 404 / `www.youtube.com` / `text/html` | Not Atom; no returned identity or entries | Not assessable | Disabled: candidate feed returned 404 |
| DW News | `UCknLrEdhRCp1aegoMqRaCZg` | 200 / `www.youtube.com` / `text/xml` | Valid Atom, title/author `DW News`, matching `yt:channelId`, 15 usable; 15/15 required fields | Predominantly English | Enabled |
| France 24 English | `UCQfwfsi5VrQ8yKZ-UWmAEFg` | 200 / `www.youtube.com` / `text/xml` | Valid Atom, title/author `FRANCE 24 English`, matching `yt:channelId`, 15 usable; 15/15 required fields | Predominantly English | Enabled |
| CBC News | `UCuFFtHWoLl5fauMMD5Ww2jA` | 200 / `www.youtube.com` / `text/xml` | Valid Atom, title/author `CBC News`, matching `yt:channelId`, 15 usable; 15/15 required fields | Predominantly English | Enabled |
| PBS NewsHour | `UC6ZFN9Tx6xh-skXCuRHCDpQ` | 200 / `www.youtube.com` / `text/xml` | Valid Atom, title/author `PBS NewsHour`, matching `yt:channelId`, 15 usable; 15/15 required fields | Predominantly English | Enabled |
| teleSUR English | `UCeYq7r_8p6N0aI704y67q1A` | 404 / `www.youtube.com` / `text/html` | Not Atom; no returned identity or entries | Not assessable | Disabled: candidate feed returned 404 |
| Africanews English | `UCU_n-m_tW_UuL8c6p3V3l4w` | 404 / `www.youtube.com` / `text/html` | Not Atom; no returned identity or entries | Not assessable | Disabled: candidate feed returned 404 |

The four failed IDs are preliminary candidates that differ from the corrected IDs recorded in `APP_CONTEXT.md`. They remain disabled because this phase audits only the explicitly supplied candidates and does not scrape pages or perform unofficial replacement lookup.

## Eligibility and affinity

Every enabled fixed feed is eligible for every valid country. Provider regions never exclude a feed or restrict which country names can match.

Natural Earth `region` and `subregion` fields still produce a small country affinity set: Europe, Africa, Asia-Pacific, Middle East, North America, or Latin America and Caribbean. Turkey, Russia, Egypt, Cyprus, and Mexico retain reviewed multi-region affinity exceptions. Iran is explicitly routed to the Middle East because the bundled Natural Earth metadata labels it Southern Asia. Article affinity is used only after match class as a deterministic ordering tie-breaker. A European article provider can therefore produce an Iran result, and a Latin American provider can produce a United Kingdom result.

YouTube routing is intentionally narrower: only enabled channels whose coverage regions intersect the selected country's routing groups are requested. A missing route is a normal empty result. Video country filtering reuses the same reviewed alias, token-boundary, collision, acronym, and multi-country matcher, but reads titles only; descriptions are neither retained nor searched.

## Country matching

Feed entries are normalized to title, HTTPS link, item-level publisher, UTC publication time, and safe plain-text summary before matching. Script and style content is discarded. Unicode is normalized, combining marks are removed for comparison, apostrophes and dashes are standardized, punctuation becomes spacing, and complete words or phrases are required. Longer aliases claim overlapping text before shorter aliases, preserving Guinea, Congo, Korea, Oman/Romania, and Niger/Nigeria collision protections while allowing explicit multi-country matches.

Evidence has three ordered classes:

1. `headline_country`: canonical country names, reviewed stable name aliases, and case-sensitive acronyms in the title.
2. `headline_related`: reviewed demonyms and canonical capital names in the title.
3. `summary_country`: country names, reviewed name aliases, demonyms, and case-sensitive acronyms in the sanitized feed summary.

Capital names are title-only and never produce summary matches. `data/country_news_aliases.json` separates stable names, related terms, and acronyms. It does not contain people, governments, arbitrary cities, or organizations. Iran/Iranian and Turkey/Türkiye/Turkiye/Turkish are explicit. Bare Georgia, Jordan, Chad, and Turkey remain suppressed because they collide with a state, person, name, or food; their reviewed demonyms, unambiguous name forms, and canonical capitals remain available. Bare Congo and Korea are omitted in favor of specific country forms.

Matching is deterministic evidence for filtering, not a relevance, truth, popularity, or sentiment score. It can still miss unconfigured local-language names and uncommon demonyms.

## Retrieval and cache boundary

`news/services/fetch.py` accepts only registry-owned URLs. It requires HTTPS on the standard port, validates allowlisted hosts and public DNS results, revalidates every redirect, and caps redirects, response bytes, and request time. Conditional `ETag` and `Last-Modified` headers are reused when supplied.

The browser requests articles from `/news/countries/<ISO2>/` and videos from `/news/countries/<ISO2>/videos/`. Django validates both through canonical country data and normalizes lowercase codes. Neither endpoint accepts a feed URL, channel ID, watch URL, embed URL, or iframe URL. Automated tests use local RSS, Atom, RDF, and YouTube Atom fixtures plus mocked fetchers; they do not contact live publishers or YouTube.

Create the existing database-cache table once after setup:

```powershell
.venv\Scripts\python.exe manage.py createcachetable
```

Google keys use `news:v<schema>:google_country:<ISO2>:<edition>`. Fixed feed keys use `news:v<schema>:rss:<feed_id>:<language>`. Raw fixed-feed snapshots are country-neutral and contain provider/feed attribution but no matched country codes, match evidence, match class, or stale presentation state. A fresh feed snapshot is reused across every country.

YouTube keys use `news:v<schema>:youtube:<source_id>:<language>`. Each channel is fetched and cached independently before country filtering, so switching between countries in one channel's route reuses the same fresh normalized snapshot. Corrupt values are discarded and fetched again. Successful entries are retained for 24 hours as stale fallback, and each channel has an independent 60-second failure backoff and process lock. Cold eligible channels use at most `NEWS_YOUTUBE_WORKERS` concurrent requests and return after `NEWS_YOUTUBE_FETCH_WAIT_SECONDS`; one failed or timed-out channel does not hide another. `NEWS_YOUTUBE_PER_CHANNEL_LIMIT` and `NEWS_YOUTUBE_TOTAL_LIMIT` bound rendered results.

Successful snapshots are fresh for approximately 15 minutes. Google stale content is retained for three days; fixed-feed stale content is retained for 24 hours. Each feed has independent conditional headers, failure state, 60-second backoff, and process lock. One failed sibling cannot invalidate another. A provider is `partial` when at least one sibling is usable and another fails, and `unavailable` only when none of its enabled siblings is usable. Google remains independent of every regional provider.

A cold request can fan out to all 13 enabled feeds. Work is bounded to `NEWS_REGIONAL_WORKERS` concurrent requests and the aggregate waits at most `NEWS_REGIONAL_FETCH_WAIT_SECONDS`; unfinished feeds become scoped failures for that response. A fully warm request performs no fixed-feed network calls and only filters cached snapshots. This is a request-time compromise for a local app without workers, Redis, or scheduled refreshes.

The cache is a rolling snapshot, not an article database or archive. Items disappear as upstream feeds roll forward or cached snapshots expire. The app cannot provide historical completeness, durable search, or guaranteed recovery of an article removed from a feed.

## Merge, ordering, and presentation

Sibling feeds are merged under their provider before country filtering. Duplicate preference is exact normalized URL, then exact normalized title plus provider, then the conservative combination of exact normalized title, explicit item publisher, and publication time. The metadata-complete item wins; all contributing sibling section labels are retained. Similar headlines from distinct publishers remain separate.

Regional ordering is match class, regional affinity, valid publication time newest first, provider display priority, original feed order, provider ID, and feed ID. Match class and affinity are evidence and tie-breakers, not editorial rankings. Limits apply independently through `NEWS_REGIONAL_PER_FEED_LIMIT`, `NEWS_REGIONAL_PER_PROVIDER_LIMIT`, and `NEWS_REGIONAL_TOTAL_LIMIT`.

The drawer identifies the provider prominently and contributing sections secondarily. Summary-only matches are labeled and show the safe feed summary. Provider-level partial and unavailable states name a provider once rather than duplicating it per sibling feed. Google News and Regional publishers controls filter already-rendered content and do not trigger network requests. The normal empty state says that no country references were found in the current feed snapshot; it does not imply that no relevant reporting exists.

Changing normalization or cache shape requires incrementing `NEWS_CACHE_SCHEMA_VERSION`.

## YouTube adapter, drawer, and player

`news/adapters/youtube.py` accepts only a configured YouTube source and a namespaced Atom `<feed>`. It verifies feed-level and entry-level channel identity, validates video IDs against `[A-Za-z0-9_-]{11}`, removes duplicate IDs, converts the title to plain text, parses a timezone-aware publication time when valid, and records original feed order. It does not retain descriptions, feed iframe markup, arbitrary links, or arbitrary thumbnails. Watch, privacy-enhanced embed, and thumbnail URLs are constructed from the validated ID:

- `https://www.youtube.com/watch?v=<VIDEO_ID>`
- `https://www.youtube-nocookie.com/embed/<VIDEO_ID>`
- `https://i.ytimg.com/vi/<VIDEO_ID>/hqdefault.jpg`

Articles is the default country-drawer tab and retains the existing Google/Regional controls. Opening Videos performs the first lazy request for that selected country. Returning to loaded Videos reuses its markup, while selecting another country resets to Articles and invalidates or aborts both request families. Request IDs and selected-country checks prevent a late response from replacing another country's panel.

The player shell is outside `#app-content` and owns the only player controller. A validated Play button dispatches a custom event containing the video ID and plain title/channel text. The once-initialized controller validates the ID again, creates a `www.youtube-nocookie.com` iframe only after that click, and updates labels through `textContent`. It supports replace, minimize/restore without replacing the iframe, close with iframe removal, and a derived HTTPS YouTube link. HTMX Map, Journal, and Settings swaps cannot remove the iframe; a full browser refresh intentionally clears playback. Theme changes do not recreate it.

The iframe uses `allowfullscreen`, `strict-origin-when-cross-origin`, and only `autoplay`, `encrypted-media`, and `picture-in-picture` capabilities. It has no sandbox or postMessage/API bridge. Thumbnail failures reveal a stable fallback. Feed text is Django-escaped, and external links use `target="_blank"` with `rel="noopener noreferrer"`. Opening Videos may lazily retrieve visible thumbnails from `i.ytimg.com`, but it does not create an iframe. The privacy-enhanced embed is created only after Play, which connects the browser to YouTube.

YouTube feeds expose only a small rolling set of recent uploads. A country can legitimately have no title match, and title-only matching can miss videos that mention a country only in their description, spoken content, local-language name, or uncommon alias. Empty results are not evidence that a channel has no relevant coverage.

## Adding a provider or feed

1. Make one bounded verification request to each official candidate and record status, redirects, hosts, content type, parsed format/title, usable item count, language, sampled fields, and date.
2. For sibling feeds, record exact normalized URL and title overlap. Do not substitute an unofficial proxy or scrape a homepage when a candidate fails.
3. Add provider metadata once. Add each independently enabled endpoint as a feed with a stable feed ID and section label.
4. Add local fixtures for newly encountered formats. Tests must use mocked fetchers only.
5. Add aliases only when collision-safe. Keep stable names, demonyms, and acronyms in their respective fields; capitals come from canonical data.
6. Run `.venv\Scripts\python.exe manage.py check` and `.venv\Scripts\python.exe manage.py test`, then verify cold, warm, empty, partial, unavailable, summary-match, filter, navigation, theme, and mobile behavior in a fresh browser session.

## Adding a YouTube channel

1. Obtain an official candidate channel ID without scraping a channel page in application code or using an unofficial lookup service.
2. Make one bounded request to its official Atom URL. Record HTTP status, final host, content type, valid Atom state, title, author, returned `yt:channelId`, usable count, required entry fields, language, and verification date. Retry once only for an obvious transient failure.
3. Enable it only when publisher identity and returned channel identity match the intended channel and recent entries normalize. Otherwise retain it disabled with the exact reason.
4. Add the stable source record with the exact channel homepage, regional route, `www.youtube.com` allowlist, neutral notes, and priority. Never add a browser-supplied URL path.
5. Add or update a local Atom fixture for new structural behavior. Automated tests must mock all HTTP.
6. Run the full checks and verify lazy loading, fresh-cache reuse, stale and partial states, validated playback, persistence across HTMX navigation, close behavior, all three themes, and desktop/mobile geometry.
