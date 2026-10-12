# How to use

On this page I will describe the main parts of World Journal and the details that are useful when you start building your own research collection.

## 1. Map

The Map is the main way to explore the app. Select a country to open its drawer, then move between Overview, Articles, Videos and Notes without losing the selected country.

### 1.1 Map Types

World Journal has three map types:

- **Terrain** uses the configured external map style for familiar geographic detail.
- **Simple** uses bundled country geometry and removes roads, buildings and other unnecessary layers.
- **Adventure** turns the world into an illustrated maritime atlas with its own colors, textures and artwork.

Your map type, camera position and display choices are remembered by the browser.

### 1.2 Country Overview

Overview shows bundled facts such as the capital, population, area, languages, currency and government when those facts are available. The facts are stored with the app, so opening an Overview does not make a live request to a facts service.

The map contains 238 ISO-backed entries and 14 custom territories from the pinned Natural Earth dataset. Custom territories can have their details edited locally. Their `X` identifiers belong only to World Journal and are not official ISO assignments.

### 1.3 Articles and Videos

Articles combines a Google News country search with matching stories from enabled regional feeds. Videos uses public YouTube channel feeds. Every item keeps its publisher or channel visible.

A source can fail without making the whole country drawer fail. If a previous successful result exists, the app can continue showing that cached result with a warning.

> **Note:** Matching is a useful filter, not a claim that every relevant story was found. Regional items are matched through reviewed country names and aliases rather than by downloading article bodies.

### 1.4 Favorites and Presets

Favorite countries from the drawer so they are easier to recognize and revisit. Favorites are shared data stored in SQLite.

Color presets let you create named country groups, assign colors and add group titles for the legend. The preset editor also lets you select countries directly on the map.

## 2. Journal

The Journal is the permanent research space. News cache and archives can expire, but entries you explicitly save remain until you delete them.

### 2.1 Entries and Collections

An entry can be a Note, Article, Video or Bookmark. New saves are placed into the matching automatic collection unless you choose another collection.

Entries support:

- Markdown text;
- ordered subsections;
- one or more country tags;
- article and video references;
- YouTube timestamps;
- event dates;
- local images;
- favorite and pinned states.

### 2.2 Writing and Autosave

While editing an existing entry, changed content autosaves approximately once per minute. The status near the editor tells you whether the current version is saved. Explicit Save buttons remain available when you want to finish immediately.

Valid YouTube links written in Markdown become player controls. They do not create automatic third-party iframes inside the entry.

### 2.3 Country References

Use `[[Romania]]` or another exact country name in Markdown to create a country link. Known aliases and canonical names are resolved when the entry is saved. Unrecognized text remains visible instead of being guessed.

Country statistics use explicit country relationships. A country name appearing in ordinary prose does not silently change the statistics.

### 2.4 Search, Filters and Statistics

The Journal can be searched and filtered by collection, entry type, country, event date, creation date and favorite state. Statistics summarize entries by type, collection, country and time period, and the totals link back to the relevant filtered list.

## 3. News

The News page provides a broader reading board outside a single country drawer. Use its tabs and filters to move between current results and the rolling archive.

### 3.1 Sources

World Journal supports:

- Google News country and world RSS searches;
- curated RSS and Atom feeds;
- public YouTube channel feeds;
- custom RSS feeds and YouTube channels added in Settings.

Go to **Settings > Sources** to enable or disable sources, add custom ones, inspect health and request a refresh.

### 3.2 Archive

Article and video metadata is kept in a rolling 90-day archive. The archive is bounded to 50,000 items and an approximate 100 MiB metadata budget. It does not download article bodies, publisher pages or video files.

Save anything important to the Journal rather than relying on the archive as permanent storage.

## 4. Countries

Countries provides a searchable and sortable directory of the same places used by the Map and Journal. Favorites appear in their own section, and each country has larger Overview, Articles, Videos and Notes views.

Selecting a custom territory exposes **Edit details** in Overview. Local edits can change its display name and facts without changing its stable identifier or existing relationships.

## 5. Video Player

Press Play on a supported YouTube item to load it into the shared player. The iframe is only created after that action and uses the privacy-enhanced YouTube domain.

The player can be moved, minimized, expanded and closed. It lives outside the page area replaced during navigation, so the same video can continue while you move between Map, Journal, News, Countries and Settings.

Use the bookmark control to save the current video and continue writing in the Journal.

## 6. Settings

Settings is divided into Preferences, Backup, Sources and Information.

- **Preferences** controls the theme, home country, map type and map labels.
- **Backup** exports or imports portable personal data.
- **Sources** controls feeds, channels, refresh timing and source health.
- **Information** collects application and data-source information.

Themes and visual map preferences belong to the current browser. Journal entries, favorites, presets, source choices and territory edits are shared through SQLite.
