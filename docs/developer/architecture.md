# Architecture

This page outlines the technologies used by World Journal and how the repository is divided.

## Tech Stack

World Journal is a monolithic Django application. The goal is to keep local installation understandable while still preserving a persistent map and video player in the browser.

- **Backend:** Django 5.2 on Python 3.13
- **Database:** SQLite
- **Templates and navigation:** Django templates with HTMX partial navigation
- **Frontend:** Vanilla JavaScript and CSS
- **Map:** Bundled MapLibre GL JS with local Natural Earth geometry
- **Feeds:** RSS and Atom through `feedparser`, fetched with `httpx`
- **Journal formatting:** Markdown rendered with `markdown-it-py`
- **Images:** Pillow validates local uploads

There is no Node build, separate frontend project, Redis, Celery or required cloud service.

## Application Structure

The Django apps follow the main data ownership boundaries:

- **`core`** owns the persistent shell, top-level pages and portable backups.
- **`countries`** owns country identity, custom territories, favorites, profiles and map presets.
- **`news`** owns source configuration, feed adapters, caching, matching, refreshing and the rolling archive.
- **`journal`** owns entries, collections, subsections, attachments, search and statistics.

Templates live under `templates/`, browser modules under `static/js/`, styles under `static/css/` and reviewed data files under `data/`.

## Persistent Shell

`templates/core/app_shell.html` contains the header, `#app-content`, video player, notification rack and shared confirmation dialog.

HTMX replaces `#app-content` while normal direct URLs continue to return full documents. `static/js/page_memory.js` retains the latest Map, Journal, News and Countries nodes so state survives navigation without keeping an unlimited page cache.

The Map is suspended rather than destroyed while another section is visible. Returning reuses the same MapLibre canvas and camera. The shared video iframe remains outside the swap target and can continue playing.

## News Pipeline

Provider-specific code lives behind feed adapters. The rest of the app works with normalized article and video records.

A small scheduler in `news/services/background.py` starts with Django and uses bounded daemon threads. General workers refresh due feeds while a separate priority lane handles selected countries. Successful snapshots are kept in Django's database cache so stale results can remain available after a temporary failure.

The normal interval is 12 hours plus a per-feed random 1 to 30 minutes. Repeated failures back off. Google requests are paced globally, and rate limits pause Google work without stopping unrelated RSS or YouTube feeds.

## Minimal Dependencies

Runtime dependencies stay in `requirements.txt`. Documentation tools remain separate:

```text
-r requirements.txt
mkdocs-material==9.*
```

Build the documentation with:

```sh
python -m mkdocs build --strict
```

Use `python -m mkdocs serve` for a local documentation preview.

## External Services

World Journal can browse bundled maps and facts without a live facts API. Current news and video metadata still depend on publishers, Google News, YouTube feeds and the configured Terrain map resources.

Those services are treated as replaceable inputs. Failures are scoped to the relevant section and do not remove local Journal data.
