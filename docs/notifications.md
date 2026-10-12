# Notifications and confirmations

The persistent shell owns `static/js/notifications.js` and `static/css/notifications.css`. Every page and theme uses the same solid semantic colors: bright green for success, orange for loading/warnings, red for errors, and blue for information. Notices use concise text without icons or dismiss buttons. Confirmation dialogs use the orange action-needed surface with named Cancel/Delete/Remove choices.

Feedback stays visible across HTMX page navigation. It is bounded to four active notices and four fading-out nodes; repeated IDs update in place. Notices fade in and out, including programmatic dismissal. Plain success/info notices expire after roughly 4.5–6 seconds, warnings after 10 seconds and errors after 12 seconds. Required retry actions and ongoing work remain until acted on or resolved; optional navigation actions expire. Hovering or focusing pauses expiry. Progress starts after 800 ms so quick operations do not flash a popup. Reduced-motion preferences disable the transitions.

Meaningful actions include explicit Journal saves, quick bookmarks, image uploads/deletions, collection/preset changes, source checks/removal, import results, and user-requested feed refreshes. A manual refresh is followed across page navigation and reports aggregate completion or partial failures. Automatic feed refresh, individual country/tab loading, favorite successes, theme changes and successful autosaves stay quiet. Autosave failures keep the draft and offer Retry save. Source/favorite write failures, major page-loading failures and interrupted HTMX requests provide actionable feedback.

Django messages are delivered by `core.views.render_page`: initial requests use the shell's JSON message payload and a no-JavaScript fallback; HTMX responses use an `HX-Trigger` event. Form validation remains next to its fields, accompanied by one warning for an unsuccessful submission. No message HTML is interpreted by the notification controller.

Deletion links still fetch the existing server confirmation, but HTMX intercepts that response before it replaces the page or pushes history. The native dialog shows the server-provided title and consequences. Its Delete button submits the same CSRF-protected form and required consent. Cancel/Escape keep the underlying screen and restore focus. A failed deletion leaves the dialog open for retry/cancel. Direct confirmation URLs and no-JavaScript submissions retain the server-rendered confirmation page. Custom-source removal and discarding/reloading populated preset drafts use the same dialog. Backup preview and import validation remain intact.

Public helpers: `notify({id, kind, title, message, action, duration})`, `dismissNotice(id)`, `updateNotice(id, message)`, `beginTask(title, options)` (returns a finish callback), and `confirmAction({title, message, accept})` (resolves a boolean). Actions may have a same-app `href` or a `run` callback. Each caller must finish its delayed progress in `finally`. Forms can provide `data-task-label`; explicit confirmation forms can provide `data-confirm-title`, `data-confirm-message`, and `data-confirm-accept`.

Map preference changes in Settings (map type, home country, general labels and terrain options) show a green Preferences saved notification after local storage succeeds. Rapid changes replace the same notice. The inline Map status is reserved for loading/errors and hidden when empty. Map gestures and display controls remain quiet; storage failures show a warning instead of a success notification.

## Manual review

- Hard-refresh, save an entry, quick-save an article/video, and open it using the notification action. Check that feedback appears once and navigation preserves the player.
- Try Delete on a disposable entry, collection, image and preset. Cancel and Escape should keep the page and URL; confirm should delete and return to the appropriate screen. Try removing a custom source, and discarding/reloading a changed map preset.
- Use Add and check with a working and a failing source. Run Refresh now, navigate away, and wait for one aggregate completion notice. Routine background refresh should not generate popups.
- Preview/import a backup and submit an invalid form. Check the progress notice, import result and field-level errors. Original import confirmation remains required.
- Stop the local server during a save/deletion. Check the error, preserved draft and retry/cancel controls; restart and retry. Successful autosaves should remain inline.
- Check dark/light/brown themes, a 390 px viewport, keyboard focus, Escape, and reduced motion. Notice colors must be identical across themes. Check fade-in/out, automatic dismissal without icons/X buttons, and rapid preference changes reusing one notice. Notices should fit without moving page content.

No database migration or additional dependency is required. Notifications are browser-session UI, not a stored inbox.
