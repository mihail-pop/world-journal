# How it works

On this page I will explain the high-level flow of World Journal and the choices behind how it stores and refreshes information.

## 1. Where the Data Comes From

The country catalog and map geometry are bundled with the app from a pinned Natural Earth dataset. Country facts are also bundled as reviewed snapshots rather than fetched every time a page opens.

Current news comes from external feeds:

- Google News RSS for broad country and world searches;
- RSS or Atom feeds published by regional news organizations;
- public YouTube channel feeds for recent videos.

The app stores article and video metadata from those feeds. Selecting an article opens its Google News link or publisher page. For Google News results, World Journal can pick a related article from a publisher that generally offers free access when the feed includes one.

## 2. Local Storage

Personal data is saved in a local SQLite database. Uploaded journal images are stored in the local `media/` folder.

This includes entries, collections, country tags, favorites, map presets, source preferences and custom territory edits. No external personal-data service is involved.

Optional authentication uses a Django administrator account as one gate around the whole installation. It does not create separate data for each account. Everyone who is allowed into one installation shares the same journal and settings.

The installation shares its theme, font, home country, map display settings and active color preset across browsers. Each browser stores its own map camera and player layout.

## 3. Feed Refreshing

A scheduler starts when the app is opened and runs inside Django while the server is active. It refreshes enabled feeds with a small worker pool and keeps its progress across server restarts.

Publisher feeds and YouTube channels use the interval from **Settings > Sources**, with options from two to twelve hours and a six-hour default. Google News uses a 24-hour interval. Both add one to five minutes to the next scheduled check. Google also has a separate delay between requests, which you can review or change with the info button next to **Refresh News**.

Publisher and YouTube feeds take priority over Google News. Google checks frequently selected countries first in a new sweep and resumes an interrupted sweep from where it left off. Failed feeds retry at their normal interval or a later time requested by the publisher. Cached results can remain available in the meantime.

> **Note:** The scheduler is intentionally part of the Django process. World Journal does not require Celery, Redis or a separate worker service.

## 4. Page Memory

World Journal uses Django templates and HTMX rather than a separate frontend application. Normal URLs still work directly, while top-level navigation replaces only the main content area.

The browser retains one Map, Journal, News and Countries workspace. This is why the map canvas, camera, selected country, loaded tabs, reading position and unsaved Journal form can survive a trip to another section.

The video player and notifications belong to the persistent shell. A full refresh starts a new workspace, and the player can restore its previous video and playback position from browser storage.

## 5. Reliability and Longevity

External feeds can move, fail or change format. They are kept behind adapters and source configuration so one provider does not define the entire app.

The parts that matter most are local. A feed shutting down does not remove saved Journal entries, local images, favorites or presets. The app may need a new source configuration, but your explicit research remains on your machine and can be exported in a portable backup.
