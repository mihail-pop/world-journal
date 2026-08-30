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
    if (persist) {
        saveTheme(nextTheme);
    }

    document.dispatchEvent(new CustomEvent("world-journal:theme-change", { detail: { theme: nextTheme } }));
}

export function initializeTheme() {
    const restoreTheme = () => applyTheme(readSavedTheme() ?? document.documentElement.dataset.theme, false);

    restoreTheme();
    document.querySelector("#theme-selector")?.addEventListener("change", (event) => {
        applyTheme(event.target.value);
    });
    document.body.addEventListener("htmx:historyRestore", restoreTheme);
    window.addEventListener("pageshow", restoreTheme);
}