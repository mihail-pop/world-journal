import { registerHtmxLifecycle } from "./htmx_lifecycle.js";
import { registerJournalPage } from "./pages/journal.js";
import { registerPresetEditor } from "./pages/map_personal.js";
import { registerMapPage } from "./pages/map.js";
import { registerSettingsPage } from "./pages/settings.js";
import { initializePlayer } from "./player.js";
import { initializeTheme } from "./theme.js";

function initializeApplication() {
    initializeTheme();
    initializePlayer();
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