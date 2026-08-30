import { registerHtmxLifecycle } from "./htmx_lifecycle.js";
import { registerMapPage } from "./pages/map.js";
import { initializePlayer } from "./player.js";
import { initializeTheme } from "./theme.js";

function initializeApplication() {
    initializeTheme();
    initializePlayer();
    registerMapPage();
    registerHtmxLifecycle();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeApplication, { once: true });
} else {
    initializeApplication();
}