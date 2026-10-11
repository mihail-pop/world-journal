const STORAGE_KEY = "world-journal:theme";
const THEMES = new Set(["dark", "light", "brown"]);

function saveTheme(theme) {
    try {
        localStorage.setItem(STORAGE_KEY, theme);
    } catch (error) {
        // Theme switching still works for the current page without storage.
    }
}

function readSavedTheme() {
    try {
        return localStorage.getItem(STORAGE_KEY);
    } catch (error) {
        return null;
    }
}

function applyTheme(theme, persist = true) {
    const nextTheme = THEMES.has(theme) ? theme : "dark";
    document.documentElement.dataset.theme = nextTheme;

    const selector = document.querySelector("#theme-selector");
    if (selector) {
        selector.value = nextTheme;
    }
    const choices = document.querySelector("[data-theme-choices]");
    if (choices) {
        choices.hidden = false;
        if (selector) selector.hidden = true;
        for (const button of choices.querySelectorAll("[data-theme-choice]")) {
            button.setAttribute("aria-pressed", String(button.dataset.themeChoice === nextTheme));
        }
    }
    if (persist) {
        saveTheme(nextTheme);
    }

    document.dispatchEvent(new CustomEvent("world-journal:theme-change", { detail: { theme: nextTheme } }));
}

export function initializeTheme() {
    const restoreTheme = () => applyTheme(readSavedTheme() ?? document.documentElement.dataset.theme, false);

    restoreTheme();
    document.body.addEventListener("change", (event) => {
        if (event.target.matches("#theme-selector")) {
            applyTheme(event.target.value);
        }
    });
    document.body.addEventListener("click", (event) => {
        const button = event.target.closest("[data-theme-choice]");
        if (button && THEMES.has(button.dataset.themeChoice)) applyTheme(button.dataset.themeChoice);
    });
    document.addEventListener("world-journal:page-ready", restoreTheme);
    document.body.addEventListener("htmx:historyRestore", restoreTheme);
    window.addEventListener("pageshow", restoreTheme);
}