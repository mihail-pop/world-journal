import { registerHtmxLifecycle } from "./htmx_lifecycle.js";
import { initializeNewsCache } from "./news_cache.js";
import { registerJournalPage } from "./pages/journal.js";
import { registerPresetEditor } from "./pages/map_personal.js";
import { registerMapPage } from "./pages/map.js";
import { registerSettingsPage } from "./pages/settings.js";
import { initializePlayer } from "./player.js";
import { initializeTheme } from "./theme.js";
import { registerUiControls } from "./ui_controls.js";

function initializeApplication() {
    initializeTheme();
    registerUiControls();
    initializePlayer();
    initializeNewsCache();
    registerMapPage();
    registerSettingsPage();
    registerJournalPage();
    registerPresetEditor();
    registerHtmxLifecycle();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeApplication, { once: true });
} else {
    initializeApplication();
}
