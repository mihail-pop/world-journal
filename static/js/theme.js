import { notify } from "./notifications.js";

function applyTheme(theme) {
    const root = document.documentElement;
    const changed = root.dataset.theme !== theme;
    root.dataset.theme = theme;
    for (const button of document.querySelectorAll("[data-theme-form] button[name=theme]")) {
        button.setAttribute("aria-pressed", String(button.value === theme));
    }
    if (changed) document.dispatchEvent(new CustomEvent("world-journal:theme-change", { detail: { theme } }));
}

export function initializeTheme() {
    const root = document.documentElement;
    let savedTheme = root.dataset.theme;
    let pendingSave = null;
    let saving = false;

    document.body.addEventListener("submit", async event => {
        const form = event.target;
        if (!form.matches("[data-theme-form]") || !event.submitter) return;
        event.preventDefault();

        const theme = event.submitter.value;
        const body = new FormData(form);
        body.set("theme", theme);
        pendingSave = { url: form.action, body };
        applyTheme(theme);
        if (saving) return;

        saving = true;
        // Save in order so a slow response cannot overwrite a newer choice.
        while (pendingSave) {
            const { url, body } = pendingSave;
            pendingSave = null;
            try {
                const response = await fetch(url, { method: "POST", body, headers: { Accept: "application/json" } });
                if (!response.ok) throw new Error("Theme save failed");
                const result = await response.json();
                savedTheme = result.theme;
                if (!pendingSave) applyTheme(savedTheme);
            } catch {
                if (!pendingSave) {
                    applyTheme(savedTheme);
                    notify({ id: "theme-save", kind: "error", title: "Theme could not be saved", message: "Your last saved theme has been restored." });
                }
            }
        }
        saving = false;
    });

    document.addEventListener("world-journal:page-ready", () => applyTheme(root.dataset.theme));
}
