import { readAppPreferences, writeAppPreferences } from "./app_preferences.js";

export function initializeTheme() {
    const render = () => {
        const theme = readAppPreferences().theme;
        for (const button of document.querySelectorAll('[data-theme-form] button[name="theme"]')) {
            button.setAttribute("aria-pressed", String(button.value === theme));
        }
    };
    document.body.addEventListener("submit", event => {
        if (!event.target.matches("[data-theme-form]") || !event.submitter) return;
        event.preventDefault();
        writeAppPreferences({theme: event.submitter.value});
    });
    document.addEventListener("world-journal:app-preferences-change", render);
    document.addEventListener("world-journal:page-ready", render);
    render();
}
