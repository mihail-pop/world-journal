// One-control writes are serialized; a second click replaces its queued value.
// Saves continue across page navigation, without keeping a page listener alive.
let registered = false;
const pageStates = new WeakMap();

function valueOf(input) { return input.type === "checkbox" ? String(input.checked) : input.value; }

function stateFor(page) {
    if (!pageStates.has(page)) {
        for (const input of page.querySelectorAll('[data-source-choice], [name="freshness_minutes"]')) {
            input.dataset.savedValue = valueOf(input);
        }
        pageStates.set(page, { pending: new Map(), running: false });
    }
    return pageStates.get(page);
}

function showStatus(page, text, failed = false) {
    const status = page.querySelector("[data-source-save-status]");
    status.textContent = text;
    status.classList.toggle("is-warning", failed);
}

async function savePending(page, state) {
    if (state.running) return;
    state.running = true;
    while (state.pending.size) {
        const [key, change] = state.pending.entries().next().value;
        state.pending.delete(key);
        const body = new FormData();
        body.set("csrfmiddlewaretoken", page.querySelector('[name="csrfmiddlewaretoken"]').value);
        body.set("country", page.querySelector('#news-preferences [name="country"]').value);
        body.set(change.input.type === "checkbox" ? "source_id" : "field", key);
        body.set("value", change.value);
        showStatus(page, "Saving…");
        try {
            const response = await fetch(page.dataset.saveUrl, { method: "POST", body, headers: { "X-Requested-With": "XMLHttpRequest" } });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "Could not save this choice.");
            change.input.dataset.savedValue = change.value;
            for (const row of page.querySelectorAll("[data-source-row]")) {
                const saved = result.states[row.dataset.sourceRow];
                if (!saved) continue;
                const health = row.querySelector(".source-health");
                if (health) { health.textContent = saved.label; health.classList.toggle("is-warning", saved.failed); }
                const refresh = row.querySelector("[data-source-refresh]");
                if (refresh) refresh.hidden = !saved.enabled;
            }
            for (const count of page.querySelectorAll("[data-provider-count]")) {
                const card = count.closest("article");
                count.textContent = [...card.querySelectorAll("[data-source-row]")].filter(row => result.states[row.dataset.sourceRow]?.enabled).length;
            }
            document.dispatchEvent(new CustomEvent("world-journal:data-changed", { detail: { path: "/settings/news/preference/" } }));
            showStatus(page, "Saved.");
        } catch (error) {
            if (!state.pending.has(key) && valueOf(change.input) === change.value) {
                if (change.input.type === "checkbox") change.input.checked = change.input.dataset.savedValue === "true";
                else change.input.value = change.input.dataset.savedValue;
            }
            showStatus(page, `${error.message} Your previous choice is kept.`, true);
        }
    }
    state.running = false;
}

function initialize() {
    const page = document.querySelector("[data-source-settings]");
    if (!page) return;
    stateFor(page);
    const input = page.querySelector('[name="kind"]');
    updateHelp(page, input.value);
}

function updateHelp(page, kind) {
    page.querySelector("[data-custom-source-help]").textContent = kind === "youtube"
        ? "Paste a channel link, @handle, UC… channel ID or YouTube channel RSS URL. Individual videos and playlists are not channel feeds."
        : "Paste an HTTPS article feed. RSS and Atom formats are detected automatically.";
}

export function registerSourceSettings() {
    if (registered) return;
    registered = true;
    document.addEventListener("world-journal:page-ready", initialize);
    document.addEventListener("change", event => {
        const input = event.target;
        const page = input.closest?.("[data-source-settings]");
        if (!page) return;
        if (input.matches("[data-source-health-country]")) { input.form.requestSubmit(); return; }
        if (input.name === "kind") { updateHelp(page, input.value); return; }
        if (!input.matches('[data-source-choice], [name="freshness_minutes"]')) return;
        if (input.name === "freshness_minutes" && !input.checkValidity()) {
            showStatus(page, "Choose a refresh interval from 5 to 120 minutes.", true);
            return;
        }
        const state = stateFor(page);
        state.pending.set(input.dataset.sourceChoice || input.name, { input, value: valueOf(input) });
        savePending(page, state);
    });
    document.addEventListener("submit", event => {
        if (event.target.id !== "news-preferences") return;
        // Enter in the interval field must not submit all checkboxes as a batch.
        event.preventDefault();
        event.stopImmediatePropagation();
        event.target.querySelector('[name="freshness_minutes"]').dispatchEvent(new Event("change", { bubbles: true }));
    }, true);
}
