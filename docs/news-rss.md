# Country news RSS

Phase 3B combines broad English-language country searches from Google News RSS with deterministic country references from curated regional RSS feeds. It does not configure YouTube, scrape publisher pages, rank editorial quality, or claim that any source is neutral.

## Registry model

`data/news_sources.json` uses schema 3 with three separate collections:

- `sources` contains dynamic application-owned integrations. Google News remains here because its country feed URL is generated per request.
- `providers` contains publisher identity, homepage, language, editorial region, affinity regions, display priority, and provider enablement.
- `feeds` contains an independently enabled RSS endpoint, parent `provider_id`, section label, URL, allowlisted hosts, language, verification date, disabled reason, and operational audit notes.

One provider can own one or more feeds. Feed IDs, provider IDs, and dynamic source IDs are globally unique. Every feed must reference a provider, every provider must own a feed, enabled providers must own at least one enabled feed, enabled feeds cannot belong to disabled providers, and active feed URLs cannot collide. All configured URLs must use HTTPS. An enabled feed requires complete audit metadata; a disabled feed requires an exact reason.

Views and browser code never construct or receive remote feed URLs. Google URL construction remains in `news/adapters/google_news.py` with the fixed global English edition `hl=en-US`, `gl=US`, and `ceid=US:en`. Those parameters select the Google edition; they do not establish an article's origin.

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

## Eligibility and affinity

Every enabled fixed feed is eligible for every valid country. Provider regions never exclude a feed or restrict which country names can match.

Natural Earth `region` and `subregion` fields still produce a small country affinity set: Europe, Africa, Asia-Pacific, Middle East, North America, or Latin America and Caribbean. Turkey, Russia, Egypt, Cyprus, and Mexico retain reviewed multi-region affinity exceptions. Affinity is used only after match class as a deterministic ordering tie-breaker. A European provider can therefore produce an Iran result, and a Latin American provider can produce a United Kingdom result.

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

The browser requests only `/news/countries/<ISO2>/`. Django validates the code against canonical country data. Automated tests use local RSS, Atom, and RDF fixtures plus mocked fetchers; they do not contact live publishers.

Create the existing database-cache table once after setup:

```powershell
.venv\Scripts\python.exe manage.py createcachetable
```

Google keys use `news:v<schema>:google_country:<ISO2>:<edition>`. Fixed feed keys use `news:v<schema>:rss:<feed_id>:<language>`. Raw fixed-feed snapshots are country-neutral and contain provider/feed attribution but no matched country codes, match evidence, match class, or stale presentation state. A fresh feed snapshot is reused across every country.

Successful snapshots are fresh for approximately 15 minutes. Google stale content is retained for three days; fixed-feed stale content is retained for 24 hours. Each feed has independent conditional headers, failure state, 60-second backoff, and process lock. One failed sibling cannot invalidate another. A provider is `partial` when at least one sibling is usable and another fails, and `unavailable` only when none of its enabled siblings is usable. Google remains independent of every regional provider.

A cold request can fan out to all 13 enabled feeds. Work is bounded to `NEWS_REGIONAL_WORKERS` concurrent requests and the aggregate waits at most `NEWS_REGIONAL_FETCH_WAIT_SECONDS`; unfinished feeds become scoped failures for that response. A fully warm request performs no fixed-feed network calls and only filters cached snapshots. This is a request-time compromise for a local app without workers, Redis, or scheduled refreshes.

The cache is a rolling snapshot, not an article database or archive. Items disappear as upstream feeds roll forward or cached snapshots expire. The app cannot provide historical completeness, durable search, or guaranteed recovery of an article removed from a feed.

## Merge, ordering, and presentation

Sibling feeds are merged under their provider before country filtering. Duplicate preference is exact normalized URL, then exact normalized title plus provider, then the conservative combination of exact normalized title, explicit item publisher, and publication time. The metadata-complete item wins; all contributing sibling section labels are retained. Similar headlines from distinct publishers remain separate.

Regional ordering is match class, regional affinity, valid publication time newest first, provider display priority, original feed order, provider ID, and feed ID. Match class and affinity are evidence and tie-breakers, not editorial rankings. Limits apply independently through `NEWS_REGIONAL_PER_FEED_LIMIT`, `NEWS_REGIONAL_PER_PROVIDER_LIMIT`, and `NEWS_REGIONAL_TOTAL_LIMIT`.

The drawer identifies the provider prominently and contributing sections secondarily. Summary-only matches are labeled and show the safe feed summary. Provider-level partial and unavailable states name a provider once rather than duplicating it per sibling feed. Google News and Regional publishers controls filter already-rendered content and do not trigger network requests. The normal empty state says that no country references were found in the current feed snapshot; it does not imply that no relevant reporting exists.

Changing normalization or cache shape requires incrementing `NEWS_CACHE_SCHEMA_VERSION`.

## Adding a provider or feed

1. Make one bounded verification request to each official candidate and record status, redirects, hosts, content type, parsed format/title, usable item count, language, sampled fields, and date.
2. For sibling feeds, record exact normalized URL and title overlap. Do not substitute an unofficial proxy or scrape a homepage when a candidate fails.
3. Add provider metadata once. Add each independently enabled endpoint as a feed with a stable feed ID and section label.
4. Add local fixtures for newly encountered formats. Tests must use mocked fetchers only.
5. Add aliases only when collision-safe. Keep stable names, demonyms, and acronyms in their respective fields; capitals come from canonical data.
6. Run `.venv\Scripts\python.exe manage.py check` and `.venv\Scripts\python.exe manage.py test`, then verify cold, warm, empty, partial, unavailable, summary-match, filter, navigation, theme, and mobile behavior in a fresh browser session.
