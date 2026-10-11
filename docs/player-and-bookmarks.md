# Shared player and quick bookmarks

All video entry points use the shell's single player outside HTMX content.
The small player has a transparent wrapper and no video padding. A compact bar
sits above it: Journal bookmark and minimize on the left, Play/Pause in the
center, expand, Close and the drag handle on the right. The new icons are
original Heroicons v2.2.0 paths under the existing bundled MIT license.

Expand fills the app view below the header, keeping the same iframe. The bar
floats near the bottom center; its expand icon switches to a contract icon.
Escape returns to small mode. Minimize/restore and page navigation preserve
playback; Close removes the iframe and stops it. A new video replaces it.

The drag handle uses pointer capture (mouse/touch/pen). The player stays fixed
relative to the viewport while scrolling, and is clamped below the header and
inside the screen. Its normalized position is saved locally and restored when
resizing, reopening or returning from expanded mode. Arrow keys move a focused
drag handle by 10 pixels; Shift increases this to 40. Updates use animation
frames; dragging neither remounts the iframe nor reloads its video.

Play/Pause uses YouTube's supported IFrame API, loaded on the first explicit
Play action, without an API key. The existing validated youtube-nocookie iframe
uses enablejsapi and the local origin. If the API script is blocked, the native
video controls remain usable. Unavailable embeds show an Open on YouTube link.
Reference: https://developers.google.com/youtube/iframe_api_reference

Article/video bookmarks on News, country drawers and the player share one
enhancement. Hovering the bookmark (or focusing it with the keyboard) reveals
a plus button. On touch devices it is always visible. Clicking the bookmark
opens Journal for writing; clicking plus saves immediately without navigation.
Once saved, the bookmark opens that entry for editing and plus shows a check.

Quick saves use a CSRF-protected POST and the ordinary Journal form validation
and automatic Articles/Videos collections. Country tags and publication dates
are copied when supplied by the source card. Saving the same URL/video again
reuses an existing entry and adds any supplied country tags without changing
its body, title, collection or other existing content. No migration is needed.
The browser coalesces repeated clicks and permits safe retries after a timeout.
Retained Journal lists/statistics refresh on their next visit after a quick save,
keeping their filter URL and scroll; retained editors keep their form contents.

## Manual acceptance

Restart the server and reload with Ctrl+F5. No tests or browser checks were run
during this implementation, as requested.

1. Start a video from Map, News and Journal. Check the new bar and bare iframe.
2. Pause/resume using both the bar and YouTube's controls; the bar icon should
   reflect playback. Check a video with embedding disabled for its fallback.
3. Expand/contract and Escape, minimize/restore, then navigate among all pages.
   Playback should continue. Close should stop it; another video should replace it.
4. Drag the small player to each corner, scroll, resize the window and expand/
   contract. Its position should stay in the viewport. Try keyboard movement
   and a phone-sized viewport, with the country drawer and preset legend open.
5. Hover/focus Save on an article or video, click plus and stay on the page.
   Check the Saved notice, automatic collection, metadata and country tags in
   Journal. Click the bookmark to write text on the saved entry.
6. Save the same item from its card and the player, and after a browser reload.
   It should reuse the entry. Existing notes must remain intact. Try a failed
   save/retry and deleting an entry before saving it again.
