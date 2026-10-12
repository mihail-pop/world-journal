import { registerHtmxLifecycle } from "./htmx_lifecycle.js";
import { initializeNewsCache } from "./news_cache.js";
import { registerJournalPage } from "./pages/journal.js";
import { registerPresetEditor } from "./pages/map_personal.js";
import { registerMapPage } from "./pages/map.js";
import { registerSettingsPage } from "./pages/settings.js";
import { registerSourceSettings } from "./pages/sources.js";
import { registerNewsPage } from "./pages/news.js";
import { registerCountriesPage } from "./pages/countries.js";
import { initializePlayer } from "./player.js";
import { registerJournalBookmarks } from "./journal_bookmarks.js";
import { initializeTheme } from "./theme.js";
import { registerUiControls } from "./ui_controls.js";

function initializeApplication() {
    initializeTheme();
    registerUiControls();
    initializePlayer();
    registerJournalBookmarks();
    initializeNewsCache();
    registerMapPage();
    registerSettingsPage();
    registerSourceSettings();
    registerNewsPage();
    registerCountriesPage();
    registerJournalPage();
    registerPresetEditor();
    registerHtmxLifecycle();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeApplication, { once: true });
} else {
    initializeApplication();
}
