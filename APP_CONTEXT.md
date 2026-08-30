# APP\_CONTEXT — World News Map and Journal — World Journal

> Product and implementation context for coding agents and contributors.
>
> Status: planning baseline; the application has not been implemented yet.
>
> Last reviewed: 2026-08-30.

## 0\. How to use this file

Read this file before designing or changing the application. It is the current source of truth for product scope, architecture, behavior, and important constraints.

When requirements conflict, use this order of priority:

1. Preserve the local-first, self-hosted, zero-account nature of the app.
2. Keep the application simple to install, understand, and maintain.
3. Protect source attribution, user data, and the host machine.
4. Make feed and map providers replaceable because external URLs will change.
5. Prefer a useful, honest result over pretending that an unreliable data point is authoritative.

Do not silently add a frontend framework, user-account system, paid API, Redis, Celery, Elasticsearch, Docker-only workflow, or cloud dependency. Such changes require an explicit product decision.

External feeds and ownership descriptions in this file are starting configuration, not permanent facts. Validate them before first release and periodically afterward. A dead or blocked feed must degrade gracefully, never break the app.

## 1\. Product summary

This is a small self-hosted Django application for visually following world news and keeping a personal research journal.

The main page is an interactive world map. Selecting a country opens a country panel containing:

* English-language news about that country
* regional perspectives from curated RSS sources
* recent videos from selected news organizations' YouTube channel feeds
* basic country facts with source and “as of” metadata
* favorites and personal notes connected to that country

The second major feature is a journal for collecting and connecting:

* personal notes
* article links
* bookmarks
* YouTube videos
* timestamps within videos
* local images
* event dates
* one or more countries

The app also has a Settings page and a persistent header.

### Primary goals

* Make countries the main navigation model for current affairs.
* Offer multiple visible source perspectives without claiming any source is neutral.
* Require no news API key and no YouTube Data API key.
* Link readers to the original article publisher instead of republishing articles.
* Make journal entries easy to find by country, day, month, year, and entry type.
* Remain suitable for a public GitHub repository and simple personal self-hosting.
* Work well for one or two simultaneous users on one machine.

### Non-goals

* A Google Maps replacement with routing, traffic, business search, or street-level imagery
* A mass-market hosted service
* User registration, login, permissions, private per-user workspaces, or multi-tenancy
* Scraping and republishing full article bodies
* Bypassing publisher paywalls
* Claiming that state-funded, publicly funded, commercial, or independent media are inherently unbiased
* A social network, commenting system, recommendation algorithm, or notification service
* A separate React, Vue, Angular, Svelte, or mobile application
* A promise that third-party RSS URLs will exist forever
* Automated factual adjudication of disputed territory, government legitimacy, or article truthfulness

## 2\. Users, deployment, and trust boundary

### Intended deployment

* One local Django server
* One SQLite database
* One or two people using it at the same time
* Normally bound to localhost or a trusted private LAN
* No accounts; all application content is shared
* Internet access is required for live map tiles, RSS feeds, external article links, and YouTube embeds

SQLite is appropriate for this scale. Configure a reasonable SQLite busy timeout and keep write transactions short. Do not add PostgreSQL merely for theoretical scale.

### Important no-account consequence

There is no concept of “my private data” versus “another user's data.” Anyone who can open the app can read, change, export, or delete the shared journal and settings.

The default run instructions must bind to 127.0.0.1. Documentation must warn that binding to 0.0.0.0, forwarding a port, or placing the app on the public internet exposes all journal data and write actions. Public exposure requires an authentication decision that is outside the current scope.

### Persistence split

Browser-specific presentation preferences belong in localStorage:

* theme
* home country
* map layer visibility
* simple mode
* last map center and zoom
* whether the video player is minimized

Shared content belongs in SQLite:

* journal entries
* country associations
* country favorites
* color presets
* custom country profile material
* source enable/disable choices
* app-wide source metadata overrides, if later supported

This split lets two browsers use different visual preferences even though the underlying journal is shared.

## 3\. Chosen application architecture

### Decision

Use a Django single-shell application with HTMX partial navigation and small vanilla JavaScript ES modules.

This is intentionally not a full client-side SPA. Django remains responsible for:

* URL routing
* complete HTML responses
* templates and partial templates
* forms
* validation
* CSRF protection
* persistence
* feed fetching and sanitization

HTMX enhances navigation by replacing only the main content area. JavaScript handles the map, player, theme, and small interactive controls that genuinely need client-side state.

This architecture is the best fit because it keeps one codebase and one rendering system, preserves normal URLs and progressive enhancement, and still allows the YouTube player to remain mounted while the user moves between top-level sections.

### Persistent shell

The initial response renders app\_shell.html with:

* the persistent top header
* primary navigation
* a main element with id app-content
* a persistent, closable/minimizable video-player region outside app-content
* global dialogs/toasts if needed

Top-level routes:

* / — map
* /journal/ — journal list/timeline
* /journal/new/ — create entry
* /journal/<uuid>/ — journal entry detail/edit
* /settings/ — settings

Country selection should be deep-linkable as /?country=RO, where RO is an ISO alpha-2 code. The query parameter restores the selected country and opens its panel after a direct load or refresh.

For a normal browser request, every top-level route returns a complete document. For an HTMX request, it returns only the page partial placed inside app-content. Header links use boosted HTMX navigation with:

* a target of #app-content
* URL history updates
* correct browser back and forward behavior
* a full-page fallback if JavaScript is unavailable

Do not load Map, Journal, and Settings once and hide them all in the DOM. Render only the active page. That avoids growing DOM size and page-specific event leaks as features are added.

### Persistent video behavior

The YouTube iframe lives outside app-content. Selecting a video dispatches one application event containing a validated YouTube video ID and optional start time. A single player controller updates the iframe.

Because HTMX replaces only app-content, playback can continue while navigating among Map, Journal, and Settings. Playback cannot survive a full browser refresh, a direct hard navigation, or closing the tab; do not imply otherwise.

The player must:

* start only after an explicit user action
* be closable and minimizable
* display the current video title and source
* offer “Open on YouTube”
* use the privacy-enhanced youtube-nocookie.com embed domain when practical
* show a useful fallback if embedding is disabled, removed, or geographically restricted
* never build an iframe URL from an arbitrary unvalidated URL

### Page JavaScript lifecycle

Use one small entry module plus feature modules, for example:

* static/js/app.js
* static/js/theme.js
* static/js/player.js
* static/js/htmx\_lifecycle.js
* static/js/pages/map.js
* static/js/pages/journal.js
* static/js/pages/settings.js

Page modules expose an initialize and cleanup function. Initialize after the initial DOM load and after an HTMX swap. Clean up before an outgoing partial is removed.

The map module must call MapLibre's cleanup method and remove its listeners before the map page is replaced. Save the current map position to localStorage before cleanup and restore it on return. Initialization must be idempotent so back/forward navigation cannot create duplicate listeners.

Do not use inline event-handler attributes. Prefer event delegation and custom application events.

### Dependencies

Use a currently supported stable Django release and supported Python release at implementation time. Pin dependencies for reproducible installs.

Expected small dependency set:

* Django
* feedparser for RSS and Atom parsing
* httpx for outbound HTTP with explicit limits and timeouts
* HTMX in static assets
* MapLibre GL JS and its CSS in static assets
* a maintained HTML sanitizer if feed summaries or rendered Markdown retain any markup
* a small Markdown renderer only if the Journal uses Markdown

Do not require Node, npm, Vite, or a JavaScript compilation step for normal development or deployment. Pin and vendor the small browser libraries under static/vendor, preserving their licenses. A maintainer may use tooling to update vendored files, but the app must run without a frontend toolchain.

## 4\. Suggested Django organization

Keep domain boundaries clear without creating dozens of tiny apps.

Suggested Django apps:

* core — shell, shared settings, health page, import/export
* countries — country catalog, map data, favorites, presets, country profiles
* news — source configuration, fetching, caching, normalization, matching, ranking
* journal — entries, country tagging, attachments, search, statistics

Suggested news service structure:

* news/adapters/base.py
* news/adapters/google\_news.py
* news/adapters/rss.py
* news/adapters/youtube.py
* news/services/fetch.py
* news/services/cache.py
* news/services/country\_matcher.py
* news/services/deduplication.py
* news/services/ranking.py
* news/types.py

Provider-specific parsing and URL construction must remain in adapters. Views should ask for normalized items and must not know whether an item came from Google News, RSS 2.0, RDF, or Atom.

Suggested data/configuration files:

* data/countries.json — stable country codes, names, aliases, demonyms, regions, bounds, centroids
* data/news\_sources.json — curated source metadata and feed/channel configuration
* static/data/countries.geojson or a preprocessed TopoJSON equivalent — map interaction geometry
* static/vendor/ — pinned HTMX, MapLibre, and any very small browser dependency

Validate data files at startup in development and through a management command in all environments. Invalid source configuration should identify the source and field clearly.

## 5\. Global interface and navigation

### Header

The header is always at the top and remains mounted during HTMX navigation. It contains:

* application name/logo placeholder
* Map
* Journal
* Settings
* persistent-player indicator or minimize/restore control when a video is loaded

The final project name is not decided. Do not invent a permanent brand throughout the code; keep the displayed name configurable.

### Layout

Desktop map layout:

* map occupies the main visual area
* map controls sit in a compact overlay
* selecting a country opens a side drawer/panel

Small-screen layout:

* map remains usable
* country content opens as a bottom sheet or full-width panel
* controls remain reachable by touch
* the video player docks without covering the entire interface

The header, country panel, player, dialogs, and forms must be keyboard accessible. Visible focus styles are required. Honor prefers-reduced-motion for nonessential camera and panel animation.

### Loading and errors

Do not show a blank panel while several feeds load. Render the country identity and cached/available sections first, then show per-section loading or error states.

Errors are scoped to their source or section:

* “Google News is temporarily unavailable”
* “2 regional sources could not be refreshed; showing cached results”
* “No matching regional headlines were found”

Never turn a source failure into a generic 500 page if cached or partial content is available.

## 6\. Map requirements

### Map stack

Use MapLibre GL JS as the map renderer.

Use OpenFreeMap as the initial external vector-style provider through a configurable style URL. Do not couple country selection or preset coloring to provider-specific layer names. OpenFreeMap is a replaceable default, not a guarantee of permanent free hosting.

Bundle a country geometry dataset derived from Natural Earth or another appropriately licensed source. This application-owned GeoJSON/TopoJSON source is used for:

* country click and hover
* selected-country outline
* preset fills
* simple mode
* stable ISO code lookup

This keeps the core interaction independent of the tile provider's style schema. Preserve dataset provenance and any required attribution. Use a pre-simplified world dataset suitable for browsers. Include selectable centroid markers or enlarged hit targets for microstates and tiny islands.

### Core interactions

* Drag/pan horizontally in the familiar slippy-map style.
* Render repeated world copies when the projection supports it.
* Scroll/pinch zoom and navigation controls.
* Hover highlights a selectable country.
* Click/tap selects exactly one country and opens its panel.
* The selected country remains highlighted.
* The URL becomes /?country=<ISO2>.
* Back/forward restores country selection.
* A home control returns to the configured home country.
* If no home country is configured, open at a useful whole-world view.

Use stable ISO alpha-2 codes for URLs and normal application identity. Store ISO alpha-3 where useful for dataset/API joins. Never use a mutable English country name as a database key.

### Layer controls

The user can turn these on or off independently where technically compatible:

* terrain/physical relief
* country names
* capital names
* water
* country outlines

“Terrain” means a physical-relief/hillshade layer, with optional true 3D terrain only if the configured provider offers a compatible elevation source. The terrain provider must be an adapter/configuration choice. Do not ship a development/demo elevation server as a production promise.

Changing a basemap style can discard custom layers. The map controller must re-add the country interaction, selection, and preset layers after the style-load event.

### Simple mode

Simple mode is a first-class view, not merely a CSS desaturation filter.

It shows:

* a plain background/water area
* country shapes
* country outlines
* optional country names
* optional capital names
* selection and preset colors

It hides roads, buildings, points of interest, and unnecessary geographic detail. It should continue to work if the external basemap style is unavailable because its essential geometry is bundled.

### Favorites

* A country can be favorited from the country panel.
* Favorites are shared application data.
* The map can visually mark favorites.
* The header or map controls may offer a compact favorite-country jump list.
* Favorites never alter article ranking.

### Color presets

Users can create named map presets such as “Y preset.”

A preset contains:

* name
* optional description
* country-to-color mapping
* optional default color
* optional custom icon or flag marker per country
* created and updated timestamps

Users can activate, rename, duplicate, edit, and delete presets. Only one preset needs to be active at a time in the first implementation. Country selection and hover styling must remain visually distinguishable from preset colors.

Validate colors and uploaded icon formats. Do not inject raw user CSS or arbitrary SVG markup.

### Borders and disputed geography

No single world-border dataset is politically neutral. Record the geometry source/version and state the map's boundary policy in About/Settings. Do not present the polygons as an adjudication of sovereignty. If alternative border views are ever added, treat them as an explicit later feature.

## 7\. Country panel

The selected-country panel should use these sections or tabs:

1. Overview
2. News
3. Videos
4. Notes

The top of the panel contains:

* name
* flag
* ISO code
* region/subregion
* favorite control
* close control

### Overview facts

Potential facts:

* capital
* population
* population year
* area
* official/common languages
* currency
* broad government form, only when a maintainable source is selected
* links to associated journal entries

Facts must display source and “as of” date/year. A stale value with a date is better than an unsupported “latest” claim.

Initial data strategy:

* bundle stable identity, capital, bounds, centroid, region, flag reference, and area
* optionally use the zero-key World Bank Indicators API for time-series population and selected statistical indicators
* cache remote facts
* treat REST Countries or similar services as replaceable convenience adapters, not the canonical identity layer
* keep volatile political facts such as current government formation manual or deferred until a reliable sourced workflow is chosen

Do not infer “government formation” from news headlines.

### Country pictures and personal information

User-added pictures are local journal/profile attachments, not scraped publisher images. Country-specific material should be implemented through:

* a country profile/overview note
* journal entries tagged with the country
* attachments on those entries

Avoid building a second unrelated notes system. The country panel is a filtered and contextual view of the same journal data.

## 8\. News-source philosophy

The purpose of the curated source list is viewpoint diversity and stronger regional representation, not a mathematical elimination of bias.

Publicly funded, state-owned, state-controlled, privately owned, nonprofit, and aggregator sources all have institutional perspectives. The interface must:

* identify the source on every item
* expose source region and a short neutral funding/ownership description
* allow sources to be enabled or disabled
* keep Google, regional sources, and videos visibly distinguishable
* avoid labels such as “unbiased,” “truth score,” or “quality score”
* never hide the publisher when two sources cover the same event

The source metadata is descriptive and reviewable. It must not be used as an automatic credibility score.

## 9\. Three feed families

### 9.1 Google News RSS — broad country results

Each country has a general English-language Google News RSS search.

Example shape:

https://news.google.com/rss/search?q=Romania\&hl=en-US\&gl=US\&ceid=US:en

Important distinction:

* q defines what the search is about.
* hl, gl, and ceid choose the Google News language/edition context.
* gl=RO does not by itself mean “articles about Romania.”

The adapter should build a search query from the country's canonical English name plus a deliberately small set of safe aliases/demonyms. URL-encode it correctly. Country-specific English editions may be configured only after verification.

Google News RSS is publicly reachable but is not treated as a formally versioned, guaranteed API contract. Keep all URL construction in google\_news.py. If its structure changes, only that adapter should need modification.

Google News links may pass through a Google redirect. Link to the provided result and do not build a fragile scraper merely to resolve every publisher URL.

### 9.2 Curated regional article RSS

These are the initial candidates. “Perspective note” is intentionally descriptive rather than a score. Validate the current feed, terms, and ownership metadata before enabling a release.

|Region|Source|Starting feed URL|Perspective note|
|-|-|-|-|
|Middle East|Al Jazeera English|https://www.aljazeera.com/xml/rss/all.xml|Qatar-funded international network|
|Middle East|Al Arabiya English|https://english.alarabiya.net/feed/default.rss|Saudi-owned regional network; verify current ownership wording|
|Asia/China|CGTN|https://www.cgtn.com/rss/news.xml|Chinese state media; also consult https://www.cgtn.com/subscribe/rss.html for current section feeds|
|Asia/Singapore|CNA|https://www.channelnewsasia.com/api/v1/rss-outbound-feed?\_format=xml|Singapore-based public-service news brand operated by Mediacorp|
|North America/USA|NPR|https://feeds.npr.org/1001/rss.xml|US nonprofit public-media network with mixed funding|
|North America/Canada|CBC News|https://www.cbc.ca/cmlink/rss-topstories|Canadian public broadcaster|
|Europe/Germany|DW|https://rss.dw.com/rdf/rss-en-all|Germany's publicly funded international broadcaster|
|Europe/France|France 24 English|https://www.france24.com/en/rss|French state-owned international broadcaster|
|Latin America|teleSUR English|https://www.telesurenglish.net/rss/news|Multi-state-funded regional network; runtime validation required|
|Latin America|MercoPress|https://en.mercopress.com/rss/|Private regional outlet focused on the South Atlantic and South America|
|Africa|Africanews|https://www.africanews.com/feed/rss|Pan-African brand owned by Euronews; this replaces the incomplete /feed/ URL|
|Africa|AllAfrica|https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf|Aggregator of reporting from many African publishers|

Do not claim that AllAfrica automatically translates every article. Preserve the item-level publisher information when the feed provides it.

Regional feeds are fetched once per source and reused for every country in that source's configured coverage regions. Do not re-download the same regional feed separately for every country.

### 9.3 YouTube channel Atom feeds

YouTube exposes recent channel uploads through:

https://www.youtube.com/feeds/videos.xml?channel\_id=<CHANNEL\_ID>

No YouTube Data API key is needed for this feed path. The active channel IDs below were checked against current channel pages on 2026-08-30. Several differ from the preliminary research list; use these values:

|Region|Channel|Channel ID|
|-|-|-|
|Middle East|Al Jazeera English|UCNye-wNBqNL5ZzHSJj3l8Bg|
|Asia/China|CGTN|UCgrNz-aDmcr2uuto8\_DL2jg|
|Asia/Singapore|CNA|UC83jt4dlz1Gjl58fzQrrKZg|
|Europe/Germany|DW News|UCknLrEdhRCp1aegoMqRaCZg|
|Europe/France|France 24 English|UCQfwfsi5VrQ8yKZ-UWmAEFg|
|North America/Canada|CBC News|UCuFFtHWoLl5fauMMD5Ww2jA|
|North America/USA|PBS NewsHour|UC6ZFN9Tx6xh-skXCuRHCDpQ|
|Latin America|teleSUR English|UCmuTmpLY35O3csvhyA6vrkg|
|Africa|Africanews English|UC1\_E8NeF5QHY2dtdLRBCCLA|

Do not reintroduce these preliminary IDs without re-verifying them:

* CGTN: UCgrNz-SZj64zgOUV4au9SJA
* CNA: UC83jt4dlz1Gjl58fzQrrkkA
* teleSUR English: UCeYq7r\_8p6N0aI704y67q1A
* Africanews: UCU\_n-m\_tW\_UuL8c6p3V3l4w

Channel RSS is a convenience endpoint, not a permanent service-level agreement. Source health checks must cover both the channel ID and whether recent entries parse successfully.

## 10\. Source configuration

Keep source definitions in data/news\_sources.json rather than scattering URLs across views and templates.

A source record should support:

\~\~\~json
{
  "id": "al\_jazeera\_en",
  "display\_name": "Al Jazeera English",
  "homepage\_url": "https://www.aljazeera.com/",
  "article\_feed\_url": "https://www.aljazeera.com/xml/rss/all.xml",
  "youtube\_channel\_id": "UCNye-wNBqNL5ZzHSJj3l8Bg",
  "coverage\_regions": \["middle\_east"],
  "home\_country\_code": "QA",
  "language": "en",
  "funding\_model": "state\_funded",
  "perspective\_note": "Qatar-funded international network",
  "enabled\_by\_default": true
}
\~\~\~

Required behavior:

* IDs are stable slugs.
* URLs must be HTTPS.
* Feed hosts are allowlisted from this configuration.
* Unknown fields fail validation during development.
* Duplicate IDs and duplicate channel IDs fail validation.
* Coverage regions are explicit.
* Source settings can disable a source without editing application logic.
* The settings UI may store enabled/disabled overrides; it does not need to edit every metadata field in the first release.

Keep the product's region taxonomy separate from country identity. A source may cover several regions.

## 11\. Feed retrieval, cache, and failure behavior

### Fetch server-side

The browser must request normalized news from Django. It must not directly fetch RSS because of CORS inconsistency, duplicate work, sanitization, and provider coupling.

Never fetch news for every country at map startup. Fetch only after a country is selected.

### Initial cache design

Use Django's database cache backed by the same SQLite database. Store a serializable normalized feed snapshot under a stable key:

* rss:<source\_id>
* youtube:<source\_id>
* google\_country:<ISO2>:<edition>

Each snapshot includes:

* normalized items
* fetched\_at
* last\_success\_at
* ETag
* Last-Modified
* last error summary
* parser warnings

Freshness policy:

* normal refresh interval: approximately 15 minutes
* keep stale successful content for up to several days
* when refresh fails, return stale content with a visible warning
* missing cache plus failed fetch returns a scoped empty/error state

The exact TTL is a setting, not a constant duplicated across adapters.

Use conditional requests with ETag and Last-Modified when supported. Identify the application with a reasonable User-Agent. Follow a small number of redirects. Use explicit connect/read/total timeouts and a small response-size ceiling. Four concurrent outbound requests is a sensible starting cap.

At this scale, do not add Redis, Celery, or a required scheduler. A lazy refresh on country access is sufficient. A management command for manual or cron-driven refresh may be added later but must remain optional.

Use a short per-process lock per cache key to reduce duplicate refreshes when two requests select the same country simultaneously.

### Outbound-request security

Feed fetching is an SSRF boundary.

* Fetch only configured, allowlisted feed hosts.
* Do not accept a feed URL from a query string or journal form.
* Require HTTPS except for an explicitly reviewed development exception.
* Reject redirects to private, loopback, link-local, or otherwise unsafe addresses.
* Limit redirects, bytes, and time.
* Do not execute scripts or load feed-provided HTML in a browser context.
* Log a safe error without logging private URLs or entire untrusted responses.

If bookmark preview fetching is added later, it needs its own SSRF-safe design. It is not part of the first version.

### Health page

Settings should show source health:

* enabled/disabled
* last successful fetch
* last attempt
* item count
* current error
* stale/fresh state
* a manual “Test/refresh” action

A management command should validate all configured feeds and return a nonzero exit status when required sources are structurally invalid. Network failures should be distinguished from parsing failures.

## 12\. Normalized news item

All article and video adapters return the same conceptual object:

* stable cache-level item ID
* kind: article or youtube
* source ID
* source display name
* title
* external URL
* canonical URL when safely available
* published timestamp with timezone, or null
* fetched timestamp
* plain-text short summary, or null
* image/thumbnail URL, or null
* author, or null
* YouTube video ID, or null
* matched country codes
* match evidence
* original feed item ID/GUID, or null

Never store or display arbitrary raw feed HTML. Convert descriptions to safe plain text by default. If limited formatting is retained later, sanitize through a strict allowlist.

## 13\. Country matching for regional feeds

The first classifier is deterministic and explainable. It is not an AI classifier.

### Matching data

For every country, data/countries.json contains:

* ISO alpha-2 and alpha-3
* canonical English name
* official English name
* carefully reviewed alternate English names
* demonyms
* optional safe abbreviations
* region and subregion

Examples requiring deliberate aliases:

* Türkiye / Turkey / Turkish
* Czechia / Czech Republic / Czech
* United States / U.S. / US / American
* United Kingdom / UK / U.K. / British
* Democratic Republic of the Congo / DR Congo / DRC / Congolese
* Republic of the Congo / Congo-Brazzaville
* Côte d'Ivoire / Ivory Coast / Ivorian
* Myanmar / Burma / Burmese
* Eswatini / Swaziland
* Cabo Verde / Cape Verde

### Algorithm

1. Start only with countries inside the source's configured coverage regions, plus explicitly configured exceptions.
2. Normalize Unicode, apostrophes, dashes, whitespace, and case.
3. Match the title first.
4. Use Unicode-aware word/token boundaries, not naive substring search.
5. Evaluate longer and more specific aliases before shorter aliases.
6. Apply an explicit ambiguity/negative-rule table.
7. Allow zero, one, or several matched countries.
8. Save which alias and field caused every match.

Summary matching may be an optional setting but is off by default. It increases recall and false positives. Never download the article body for classification.

### Ambiguities that need tests

* Georgia the country versus the US state
* Jordan the country versus a person
* Chad the country versus a person's name
* Turkey the country versus the bird
* Niger versus Nigeria
* Guinea versus Guinea-Bissau or Equatorial Guinea
* Congo versus the two Congo states
* US versus lowercase “us”
* Mali versus personal names
* Oman inside another token

Region restriction reduces mistakes but does not eliminate them. Keep a test fixture containing known positive and negative headlines for each ambiguous alias.

Country matching is a convenience filter, not a claim that every relevant story was found. The UI should say “Matched regional headlines,” not “All news from this country.”

## 14\. Deduplication, ordering, and “trending”

RSS feeds usually do not expose a comparable popularity score. Do not invent one.

Default country-news presentation:

* Google News — its own section, using feed order
* Regional perspectives — balanced recent ordering
* Videos — newest first

Balanced recent ordering:

* sort each source's items by published time
* interleave sources round-robin
* cap consecutive items from one source
* place items without dates after dated items
* show a clear source badge

Offer “Newest” as an alternate regional sort. Do not call either mode “trending.”

Deduplicate only clear repeats:

* same source plus same GUID/link
* same source plus normalized title in a short time window
* exact canonical URL repeats

Do not delete a second publisher's coverage merely because its headline resembles another publisher's headline. A later story-clustering feature may group related coverage, but every source remains visible inside the cluster.

## 15\. Article display and copyright boundary

Article cards may display only what is reasonably supplied for syndication by the feed:

* title
* source
* publication time
* short feed-provided summary
* feed-provided image when its terms permit display

The primary action opens the publisher/Google News result in a new tab with safe rel attributes. Do not iframe normal news websites. Many publishers block framing, and framing creates privacy, security, usability, and terms problems.

Do not:

* scrape the full article
* strip paywalls
* copy the full publisher page
* proxy publisher images merely to evade hotlink controls
* imply the article was written by this app

Always retain source attribution. If a feed's terms allow personal reading but restrict republication, follow those terms and document the implications for people who redistribute or publicly host the project.

## 16\. YouTube video behavior

Parse YouTube's Atom fields and extract only a validated video ID, title, channel, published time, link, and thumbnail metadata.

Country filtering uses the same explainable title matcher as article feeds. A video can match multiple countries.

When the user selects a video:

* load it in the persistent player
* preserve playback while HTMX top-level navigation swaps app-content
* provide a copy/open link
* allow a Journal entry to reference the video
* allow an integer start time in seconds

For journal timestamps:

* store seconds as the canonical value
* display friendly HH:MM:SS or MM:SS
* validate that the value is nonnegative
* initialize the embed with the start value

The Content Security Policy should permit frames only from the selected YouTube embed domains. Thumbnails and remote feed images need similarly narrow image rules or should be proxied only through an explicitly safe image design.

## 17\. Journal

### One unified journal

There is one journal. Country notes are journal entries associated with countries, not a parallel notes database.

An entry can represent:

* note
* article link
* bookmark
* YouTube video
* mixed research entry

An entry can be associated with zero, one, or many countries.

### Conceptual entry fields

* UUID
* title
* body
* entry type
* source URL, optional
* YouTube video ID, optional
* YouTube timestamp seconds, optional
* event date, optional
* event-time precision if needed later
* created\_at
* updated\_at
* countries, many-to-many
* favorite/pinned state
* local attachments

Use event\_date for “this note concerns 20 August 2025.” Keep it separate from created\_at, which answers “when did I save it?” Month/year filters use event\_date by default and offer created date as a secondary filter.

### Writing format

Markdown is a good fit if implemented with a small maintained renderer:

* store the original Markdown
* sanitize rendered output
* disable raw HTML
* do not allow arbitrary iframe markup
* represent videos as structured fields/cards

If Markdown is not included initially, start with plain text rather than a rich-text editor dependency. The data model should not assume stored HTML is trusted.

### Country links

Support explicit wiki-style country references such as:

\[\[Romania]]

On save/render:

* resolve only exact configured country names/aliases
* render a link to /?country=RO
* associate the entry with that country, or clearly prompt/add the tag
* keep unresolved text visible rather than guessing

Statistics count explicit country associations. Plain text country mentions may produce suggestions later but should not silently affect statistics.

### Journal views

* chronological list/timeline
* entry detail/edit
* search
* filter by event day/month/year
* filter by created day/month/year
* filter by one or more countries
* filter by entry type
* filter favorites/pinned
* country page filtered view

The URL should reflect active filters so refresh and back/forward work.

### Bookmarks and links

Pasting an article URL creates a structured link field plus optional manually entered title/source. Automatic metadata scraping is deferred because it adds SSRF, parser, and publisher-policy complexity.

A future “Save to Journal” action on an in-app news card can safely copy:

* title
* source
* feed link
* published time
* selected country

It must not copy the full article.

### Pictures

Journal/country pictures are uploaded to local media storage.

* validate MIME type by content, not only extension
* set a configurable size limit
* generate safe filenames
* never execute SVG/HTML uploads inline
* delete orphaned files deliberately
* include media in backup/export

### Search and statistics

For the initial personal-scale database, normal Django/SQLite text search is acceptable. Keep search behind a service/query layer so SQLite FTS5 can be added later if the journal becomes large.

Initial statistics:

* entries per country
* entries per day/month/year
* article/video/note counts
* most frequently associated countries

Every count should link back to the filtered Journal view. Do not call inferred plain-text mentions “mentions” unless the UI distinguishes them from explicit country tags.

## 18\. Settings

Settings sections:

### Appearance

* dark, light, or brown theme
* dark is the default
* remember theme per browser

### Map

* home country
* terrain
* country names
* capital names
* water
* country outlines
* simple mode
* reset saved viewport

### News sources

* enable/disable sources
* display source description and region
* show health and last refresh
* manual test/refresh
* cache freshness setting within safe bounds

### Data

* export backup
* import backup with preview/confirmation
* download source/country diagnostics
* optional clear-feed-cache action

Deleting journal data, attachments, presets, or an existing database is destructive and requires a clear confirmation step. Clearing feed cache is noncritical and should be labeled separately.

## 19\. Theme system

Apply the theme to the html element through data-theme. The root palette is the dark default. Load the saved theme with a tiny head script before the main stylesheet to prevent a flash of the wrong theme.

The following palette is provided by the product owner and is the source of truth:

\~\~\~css
:root {

  --bg-primary: #0b1622;
  --bg-tertiary: #151f2e;
  --bg-quaternary: #32445b;

  --text-primary: #8596a5;
  --text-secondary: #a8b5c4;

  --overlay-bg: #101820;
  --overview-border: #475a6d;
  --button-bg: #1f2a38;

  --special-color: #00bfff;
  --special-color-hover: #57d5ff;
}

\[data-theme="light"] {
  --bg-primary: #FFFFFF;
  --bg-tertiary: #F2F2F2;
  --bg-quaternary: #E5E5E5;

  --text-primary: #0F0F0F;
  --text-secondary: #606060;

  --overlay-bg: #cccccc;
  --overview-border: #f3f3f3;
  --button-bg: #ebebeb;

  --special-color: #00bfff;
  --special-color-hover: #57d5ff;
}

\[data-theme="brown"] {
  --bg-primary: #271c19;
  --bg-tertiary: #55423d;
  --bg-quaternary: #af7f76;

  --text-primary: #faeee7;
  --text-secondary: #faeee7;

  --overlay-bg: #271c19;
  --overview-border: #3b2b27;
  --button-bg: #6b534c;

  --special-color: #df5c38;
  --special-color-hover: #dd866e;
}
\~\~\~

Rules:

* Do not replace these values without an explicit design change.
* New semantic variables may be added, but derive them consistently from this palette.
* Use variables throughout; do not scatter literal theme colors through components.
* Map selection and preset colors must remain legible in all themes.
* Error, warning, success, focus, and disabled states need accessible contrast.
* Theme changes update the map's application-owned layers as well as normal HTML.

## 20\. Data backup and portability

Self-hosted personal data needs a first-class escape route.

Provide an export containing:

* versioned JSON manifest
* journal entries and country associations
* app-wide settings
* favorites and color presets
* country profile content
* media attachments

A ZIP archive is appropriate when attachments exist.

Import must:

* validate format/version before writing
* show a summary
* reject unsafe paths
* avoid overwriting the live database without confirmation
* define duplicate UUID behavior
* run inside a transaction for database records
* report attachment errors

Also document a simple manual backup: stop the server, copy the SQLite file and media directory together, then restart.

Feed cache does not need to be included in backups.

## 21\. Security and privacy baseline

Even a localhost app processes untrusted internet content.

Required controls:

* Django CSRF protection on every write
* escaped templates by default
* strict sanitization for feed summaries and rendered Markdown
* URL validation for external links
* rel="noopener noreferrer" on new-tab links
* no arbitrary iframe HTML
* validated YouTube IDs
* restrictive Content Security Policy
* remote feed allowlist and SSRF protections
* upload type and size validation
* no secrets in the repository
* no API keys in templates or JavaScript
* safe logs that do not dump feed bodies or journal content unnecessarily

If an API key is ever added for an optional provider, read it from environment configuration and keep a fully functional zero-key path.

## 22\. Performance baseline

Targets are for a normal personal computer, not a global service.

* Initial shell and bundled simple-map data should appear promptly.
* News is lazy-loaded after country selection.
* Cached country news should render without waiting on the network.
* Fetch stale sources concurrently with a small bound.
* Cap displayed items per source and paginate/load more.
* Avoid loading every journal attachment on list views.
* Use thumbnail sizes for uploaded images.
* Keep map data pre-simplified and static-compressible.
* Do not keep inactive page trees or duplicate MapLibre instances in memory.

SQLite recommendations:

* enable a practical busy timeout
* use indexes for journal event\_date, created\_at, entry\_type, and relation tables
* keep network requests outside database transactions
* paginate journal lists

## 23\. Testing expectations

### Unit tests

* source configuration validation
* Google News URL encoding
* RSS/RDF/Atom normalization fixtures
* YouTube video-ID extraction
* country alias positive and negative cases
* multi-country matching
* ambiguous-country rules
* source-aware deduplication
* date/timezone normalization
* Markdown/feed sanitization
* backup import path safety

Tests must use local feed fixtures. Normal test runs must not depend on live publishers.

### Integration tests

* full route and HTMX partial return the correct template shape
* header navigation updates history
* browser back/forward restores page and filters
* direct /journal/ load works without HTMX
* direct /?country=RO opens the correct country
* stale cache is served after a simulated provider failure
* one failed regional feed does not hide other feeds
* journal save associates countries
* import preview does not write data

### Browser tests/manual acceptance

* player continues during HTMX navigation
* player stops/closes correctly
* returning to Map creates one map instance
* map viewport is restored
* layer toggles and simple mode persist
* themes apply before first paint
* keyboard focus is usable in header, drawers, player, and forms
* mobile country panel and player do not make the app unusable

### Live-source diagnostics

Live checks are a separate opt-in management command, not part of deterministic tests. They report:

* HTTP status/content type
* parse success
* item count
* newest item date
* whether the expected YouTube channel ID is returned
* redirect/host changes

## 24\. Initial implementation order

### Phase 1 — shell

* Django project and apps
* app shell and top routes
* HTMX navigation/history
* exact three-theme system
* persistent empty player component
* localStorage preference service

### Phase 2 — map

* MapLibre with configurable style
* bundled country geometry and ISO joins
* select/hover/deep link
* home country and saved viewport
* layer controls
* simple mode
* country drawer with static identity

### Phase 3 — article feeds

* source and country configuration validation
* safe fetcher
* database cache
* feed normalization
* Google News adapter
* regional adapter
* country matcher and ambiguity tests
* article cards and source transparency
* source health in Settings

### Phase 4 — videos

* corrected YouTube channel feeds
* title filtering
* persistent player
* timestamp support
* embed failure/open-on-YouTube fallback

### Phase 5 — journal

* entry create/edit/list/detail
* event date and filters
* country associations and wiki-style links
* structured article/video fields
* local images
* “Save to Journal” from news/video cards

### Phase 6 — personal map data

* favorites
* presets
* country profile/overview note
* per-country filtered journal

### Phase 7 — portability and insights

* backup export/import
* statistics with drill-down filters
* optional better full-text search
* maintenance documentation

Do not start with every feature at once. Complete each phase with tests and a coherent usable UI.

## 25\. Decisions deliberately deferred

These are not blockers for the shell or feed architecture:

* final project name and logo
* exact physical-relief/elevation provider for terrain
* whether government-form data is manual or comes from a reviewed source
* exact country/border policy and geometry resolution
* whether multiple color presets may be layered simultaneously
* rich-text editor versus Markdown/plain text
* advanced story clustering
* bookmark metadata fetching
* public deployment/authentication
* multi-user/private journals
* notifications or scheduled digests

When one of these becomes necessary, record the decision here instead of encoding an undocumented assumption.

## 26\. Reference links

These are implementation references, not uptime guarantees:

* MapLibre GL JS documentation: https://maplibre.org/maplibre-gl-js/docs/
* OpenFreeMap quick start: https://openfreemap.org/quick\_start/
* Natural Earth downloads: https://www.naturalearthdata.com/downloads/
* Natural Earth terms: https://www.naturalearthdata.com/about/terms-of-use/
* World Bank Indicators API: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation
* CNA RSS directory: https://www.channelnewsasia.com/rss
* CGTN RSS directory: https://www.cgtn.com/subscribe/rss.html
* Al Arabiya MRSS directory: https://english.alarabiya.net/tools/mrss
* Africanews RSS directory: https://www.africanews.com/page/widgets/

## 27\. Definition of a successful first release

The first release is successful when a new self-hoster can:

1. clone the repository;
2. create a Python virtual environment;
3. install pinned Python dependencies;
4. migrate SQLite;
5. run Django locally without API keys or a frontend build;
6. open a themed interactive map;
7. select a country and see attributed Google, regional, and video results or honest per-source failure states;
8. play a selected video in the persistent player;
9. save an article/video/note to the journal with an event date and country;
10. filter the journal by country and month/year;
11. configure map preferences, source choices, favorites, and presets;
12. export the journal and local media in a portable backup.

No source, map provider, or political metadata is described as neutral or guaranteed forever. The app remains useful when individual external services fail.

