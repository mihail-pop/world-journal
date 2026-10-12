# How it works

On this page I will explain the high-level flow of World Journal and the choices behind how it stores and refreshes information.

## 1. Where the Data Comes From

The country catalog and map geometry are bundled with the app from a pinned Natural Earth dataset. Country facts are also bundled as reviewed snapshots rather than fetched every time a page opens.

Current news comes from external feeds:

- Google News RSS for broad country and world searches;
- RSS or Atom feeds published by regional news organizations;
- public YouTube channel feeds for recent videos.

The app stores normalized metadata from those feeds. It does not scrape full articles, bypass paywalls or download videos. Selecting an article opens the original result or publisher page.

## 2. Local Storage

Personal data is saved in a local SQLite database. Uploaded journal images are stored in the local `media/` folder.

This includes entries, collections, country tags, favorites, map presets, source preferences and custom territory edits. No external personal-data service is involved.

Optional authentication uses a Django administrator account as one gate around the whole installation. It does not create separate data for each account. Everyone who is allowed into one installation shares the same journal and settings.

Some presentation choices belong only to the current browser. Themes, the home country, map display settings and player position use browser storage so two browsers can keep different layouts while sharing the same journal.

## 3. Feed Refreshing

A bounded scheduler runs inside Django while the server is active. It refreshes enabled feeds in the background with a small worker pool.

The normal refresh interval is 12 hours plus a separate random 1 to 30 minutes for each feed before it becomes due. That random time is not a delay inserted between every download. Missing feeds and manual refresh requests can start promptly.

When a country is selected, its missing or due feeds receive priority. Existing cached content remains usable when a provider temporarily fails. Repeated failures back off instead of retrying continuously.

> **Note:** The scheduler is intentionally part of the Django process. World Journal does not require Celery, Redis or a separate worker service.

## 4. Page Memory

World Journal uses Django templates and HTMX rather than a separate frontend application. Normal URLs still work directly, while top-level navigation replaces only the main content area.

The browser retains one Map, Journal, News and Countries workspace. This is why the map canvas, camera, selected country, loaded tabs, reading position and unsaved Journal form can survive a trip to another section.

The video player and notifications belong to the persistent shell outside that replaced area. A full refresh still starts a new browser workspace and stops the current video.

## 5. Reliability and Longevity

External feeds can move, fail or change format. They are kept behind adapters and source configuration so one provider does not define the entire app.

The parts that matter most are local. A feed shutting down does not remove saved Journal entries, local images, favorites or presets. The app may need a new source configuration, but your explicit research remains on your machine and can be exported in a portable backup.
