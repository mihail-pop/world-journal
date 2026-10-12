# Returning to Map and Journal

The Map and Journal header links resume the last screen in the current browser tab. This is an intentional extension of the original destroy-on-navigation lifecycle, requested for switching between research and writing. No new dependency, server session, account, or background worker is involved. `APP_CONTEXT.md` retains the original planning baseline.

## What stays

- One Map instance and its actual canvas, loaded geometry/style, camera, selected country, active drawer tab, article filter, loaded articles/videos/facts, and drawer scroll position.
- One last Journal screen: filtered list, statistics, detail or editor, its URL, scroll positions, expanded controls, form values, subsections and text cursor. Changed drafts autosave about every minute; the editor displays save status.
- The existing persistent video player remains outside the swapped page and continues playback.
- Countries now retains its search, sorting, selected country/tab, loaded content
  and reading/list positions in the same way. Its active header link resets to
  the main country list. See [Countries](countries-page.md) for details.

Retained pages are detached from the visible document, not stacked as hidden pages. Map suspension stops camera animation, clears transient hover and suppresses map-specific keyboard/history interaction while another page is active. Existing bounded loads may finish into its retained drawer. Return resizes the same canvas for the current layout and restores the camera without fitting the selected country again. If Map's initial data is still loading when the user leaves, map creation waits until return.

There is one retained Map and at most one screen each for Journal, News and Countries,
rather than an accumulating cache of every visited page/editor. Other pages remain
freshly rendered. The shared swap hook preserves these workspaces when navigating
to pages using the normal `#app-content` partial lifecycle.

## Navigation and fresh data

Header links remember the last Map/Journal URL when returning from another page. Clicking the currently active header link instead opens its root screen, discards its remembered view and starts at the top. Journal changes are saved before its editor is replaced; failed saves keep that editor visible. A Map reset tears down its old canvas before creating the fresh map. Explicit country links, filtered Journal links and Save to Journal still open their specified destination. Returning through the Journal header reuses the remembered screen; navigating within Journal or submitting a form replaces it with the fresh server response. Successful Save/Delete never restores the old editor through the header.

A small HTMX extension prepares retained nodes before HTMX performs its ordinary innerHTML swap. HTMX still owns request processing, URL history and swap events. The main content opts out of HTMX's serialized history cache: canvas state and draft input values cannot reliably be serialized, and transient editors should not be copied into local storage. Back/Forward can request fresh server partials and reuse the matching retained workspace. Only the last Journal workspace is retained; returning to another Journal URL uses the server response.

Returning after local Settings changes reapplies theme/home/map preferences. Preset/favorite changes reload personal map data. Successful Journal/profile writes invalidate country Notes, which refresh when visible or next opened. News source changes invalidate the loaded article/video snapshots; normal section switching alone does not refetch them.

## Tradeoffs

The retained Map consumes browser memory and keeps one WebGL context while another page is visible. This makes return fast without recreating the map or its listeners. Existing map tile/feed requests can finish after departure; suspension is not a network shutdown. The top-level partial still makes a local Django request when a header link is used.

Workspace memory lasts only within the currently loaded tab. Refresh, closing the tab, full-page navigation or opening a link in another tab starts a fresh workspace. Check that the Journal status says Saved before refreshing or closing the tab. Unsaved changes produce the ordinary browser leave warning. Autosave protects saved content, but workspace memory is not crash recovery or an archive of old feed results. Cached screens can also differ from changes made in another browser; refresh to obtain those changes. Player playback retains its existing full-refresh limitation.

## Manual checks

Tests and browser acceptance are left to the user for this change. Start if necessary:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Hard-refresh once to load the updated shell and JavaScript, then:

1. Select Bulgaria, let Articles load, change the article filter, zoom/pan and scroll its drawer. Visit Journal, Settings and Map through the header. The same camera, Bulgaria drawer, filter and scroll should return without map-data or article/video requests restarting.
2. Load Videos or Overview and repeat. The loaded tab should remain selected. Start video playback, visit other pages and return; the persistent iframe should keep playing.
3. Filter Journal, move to another list page, scroll down, visit Map and return through the Journal header. The URL, filters and position should return. Repeat on a detail screen and on statistics.
4. Start a new entry, type text, add/reorder subsections and select countries. Visit Map and Settings, then Journal. All unsaved input and subsection structure should remain. Save: the new server detail should replace the editor, and a later header return must show the saved screen.
5. From a retained Journal screen, follow an explicit country link to a different country. It should select that country. From Map, use Save to Journal: the requested prefilled editor should open instead of a previous Journal screen.
6. Exercise Back/Forward across sections and countries, including closing the drawer. Press Escape while on Journal: it must not silently close the detached Map drawer or change the Journal URL.
7. Save an entry associated with Bulgaria and return to its Notes. It should appear without losing the Map camera or reloading unchanged Articles. Change a news-source setting or color preset and return: the corresponding data should update.
8. Repeat on a narrow layout, rotate/resize while away, switch themes, minimize/restore the player and make several round trips. Expect one map canvas, usable controls and the remembered position. Also leave Map immediately during its initial load, then return.

Fresh Journal navigation, including Statistics and Back to Journal, scrolls the browser to zero after HTMX settles. Returning from another page restores the remembered scroll and focus instead.
