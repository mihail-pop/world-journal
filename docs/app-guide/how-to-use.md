# How to use

On this page I will describe the main parts of World Journal and the details that are useful when you start building your own research collection.

## 1. Map

The Map is the main way to explore the app. Select a country to open its drawer, then move between Overview, Articles, Videos and Notes without losing the selected country.

### 1.1 Map Types

World Journal has three map types:

- **Terrain** uses the configured external map style for familiar geographic detail.
- **Simple** uses bundled country geometry and removes roads, buildings and other unnecessary layers.
- **Adventure** turns the world into an illustrated maritime atlas with its own colors, textures and artwork.

Your map type and display choices are shared across browsers. Each browser remembers its own camera position.

### 1.2 Country Overview

Overview shows bundled facts such as the capital, population, area, languages, currency and government when those facts are available. The facts are stored with the app, so opening an Overview does not make a live request to a facts service.

The map contains 238 ISO-backed entries and 14 custom territories from the pinned Natural Earth dataset. Custom territories can have their details edited locally. Their `X` identifiers belong only to World Journal and are not official ISO assignments.

### 1.3 Articles and Videos

Articles combines a Google News country search with matching stories from enabled regional feeds. Videos uses public YouTube channel feeds. Every item keeps its publisher or channel visible.

The drawer can keep showing saved results if a source fails. Check **Settings > Sources** for warnings and retry controls.

> **Note:** Matching is a useful filter, not a claim that every relevant story was found. Regional items are matched through reviewed country names and aliases rather than by downloading article bodies.

### 1.4 Favorites and Presets

Favorite countries from the drawer so they are easier to recognize and revisit. Favorites are shared data stored in SQLite.

Color presets let you create named country groups, assign colors and add group titles for the legend. The preset editor also lets you select countries directly on the map.

## 2. Journal

The Journal is the permanent research space. News cache and archives can expire, but entries you explicitly save remain until you delete them.

### 2.1 Entries and Collections

An entry can be a Note, Article, Video or Bookmark. New saves are placed into the matching automatic collection unless you choose another collection.

Entries support:

- rich text with headings, lists and tables;
- ordered subsections;
- one or more country tags;
- article and video references;
- YouTube timestamps;
- event dates;
- local images;
- favorite and pinned states.

### 2.2 Writing and Autosave

Changed content autosaves approximately once per minute. Check the save status in the toolbar or use **Save** to save immediately.

Entries with a YouTube reference can play the video inline or open it in the shared player. Use **PDF / Print** or **Word (.docx)** to export an entry.

### 2.3 Country References

Use **Countries** in the editor to link an entry to one or more places. These links make the entry available from each country's Notes tab.

### 2.4 Search, Filters and Sorting

Search the Journal or narrow the list by collection, entry type, country and **Activity Date**, which is the last time the entry was saved or updated. Sort by Activity Date, Release Date, Event Date or Title. **Rewind** jumps to the previous day with matching activity.

## 3. News

The News page brings current results and archived coverage into one list per tab. Search or filter by source and publication period, then scroll to load more.

### 3.1 Sources

World Journal supports:

- Google News country and world RSS searches;
- curated RSS and Atom feeds;
- public YouTube channel feeds;
- custom RSS feeds and YouTube channels added in Settings.

Go to **Settings > Sources** to enable or disable sources, add custom ones, inspect health and request a refresh.

### 3.2 Archive

The archive stores article and video metadata. In **Settings > Sources**, choose an archive budget of **500 MB**, **1 GB** or **2 GB**. The default is 2 GB. World Journal removes the oldest items as needed to stay within the approximate storage budget and the 3 million item safety cap. Coverage for 90 days is a storage estimate.

Save anything important to the Journal rather than relying on the archive as permanent storage.

## 4. Countries

Countries provides a searchable and sortable directory of the same places used by the Map and Journal. Favorites appear in their own section, and each country has larger Overview, Articles, Videos and Notes views.

Selecting a custom territory exposes **Edit details** in Overview. Local edits can change its display name and facts without changing its stable identifier or existing relationships.

## 5. Video Player

Press Play on a supported YouTube item to load it into the shared player. The iframe is only created after that action and uses the privacy-enhanced YouTube domain.

The player can be moved, minimized, expanded, popped out or closed. The same video can continue across app pages, and a full refresh can restore the video and playback position.

Use the bookmark control to save the current video and continue writing in the Journal.

## 6. Settings

Settings is divided into Preferences, Backup, Sources and Information.

- **Preferences** controls the theme, app font, home country, map type and map labels.
- **Backup** exports or imports portable personal data.
- **Sources** controls feeds, channels, refresh timing and source health.
- **Information** shows the installed and latest releases, with links to report an issue or ask a question.

Preferences, journal entries, favorites, presets, source choices and territory edits are shared through SQLite. The map camera and player layout are saved in the browser.
