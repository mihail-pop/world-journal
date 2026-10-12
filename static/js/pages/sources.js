// One-control writes are serialized; a second click replaces its queued value.
// Saves continue across page navigation, without keeping a page listener alive.
import { beginTask, dismissNotice, notify, updateNotice } from "../notifications.js";

let registered = false;
const pageStates = new WeakMap();
let progressController = null;
let manualRefresh = null;

function reportRefresh(result) {
    if (!manualRefresh) return;
    manualRefresh.errors = 0;
    if (result.busy) {
        updateNotice("feed-refresh", `${result.completed} of ${result.total} feeds checked. You can keep browsing.`);
        return;
    }
    manualRefresh.finish();
    clearTimeout(manualRefresh.timer);
    manualRefresh = null;
    const failures = Math.max(result.failed, result.errors.length);
    notify({id: "feed-refresh", kind: failures ? "warning" : "success", title: failures ? "Refresh finished with source notices" : "Feed refresh complete", message: !result.enabled ? "No sources are enabled." : failures ? `${failures} feed${failures === 1 ? " is" : "s are"} unavailable. Cached results are kept where available.` : "Articles and videos are ready to browse.", action: failures ? {label: "Review sources", href: "/settings/news/"} : undefined, duration: 12000});
}

function watchRefresh(url) {
    manualRefresh?.finish();
    clearTimeout(manualRefresh?.timer);
    const state = manualRefresh = {finish: beginTask("Refreshing news feeds…", {id: "feed-refresh", message: "You can keep browsing while feeds refresh."}), timer: null, errors: 0, started: Date.now()};
    async function poll() {
        if (manualRefresh !== state) return;
        try {
            if (Date.now() - state.started > 45 * 60000) throw new Error("Refresh is taking longer than expected.");
            // The existing Sources poll reports progress while that page is open.
            if (!document.hidden && (!progressController || progressController.unavailable)) {
                const abort = new AbortController();
                const timeout = setTimeout(() => abort.abort(), 10000);
                try {
                    const response = await fetch(url, {signal: abort.signal});
                    if (!response.ok) throw new Error("Refresh status unavailable.");
                    const result = await response.json();
                    if (manualRefresh === state) reportRefresh(result);
                } finally { clearTimeout(timeout); }
            }
        } catch (_) {
            if (++state.errors >= 3) {
                state.finish();
                manualRefresh = null;
                notify({id: "feed-refresh", kind: "warning", title: "Refresh status is unavailable", message: "Feeds may still be refreshing. Check the Feed cache panel for the latest status.", action: {label: "View sources", href: "/settings/news/"}});
            }
        }
        if (manualRefresh === state) state.timer = setTimeout(poll, 5000);
    }
    state.timer = setTimeout(poll, 1500);
}

function cleanupProgress() {
    if (!progressController) return;
    clearTimeout(progressController.timer);
    progressController.abort.abort();
    progressController = null;
}

function renderProgress(page, result) {
    const progress = page.querySelector("[data-refresh-progress]");
    progress.max = Math.max(1, result.total);
    progress.value = result.total ? result.completed : result.busy ? 0 : 1;
    const failed = Math.max(result.errors.length, result.failed);
    page.querySelector("[data-refresh-summary]").textContent = result.busy
        ? `Refreshing ${result.completed} of ${result.total} feeds`
        : !result.enabled ? "No feeds enabled" : failed ? `Done · ${failed} feed${failed === 1 ? "" : "s"} unavailable` : "Done · cache ready";
    page.querySelector("[data-refresh-current]").textContent = result.busy
        ? result.current.join(" · ") || "Waiting for the next feed…"
        : "";
    page.querySelector("[data-refresh-all]").disabled = result.busy;
    const details = page.querySelector("[data-refresh-errors]");
    details.hidden = !result.errors.length;
    details.querySelector("[data-refresh-error-summary]").textContent = `${result.errors.length} feed${result.errors.length === 1 ? "" : "s"} unavailable`;
    const list = details.querySelector("[data-refresh-error-list]");
    const signature = JSON.stringify(result.errors);
    if (list.dataset.errors !== signature) {
        list.replaceChildren();
        for (const error of result.errors) {
            const item = document.createElement("li");
            item.textContent = `${error.name}: ${error.error}`;
            list.append(item);
        }
        list.dataset.errors = signature;
    }
}

async function pollProgress(controller) {
    if (progressController !== controller) return;
    let busy = false;
    try {
        if (!document.hidden) {
            const response = await fetch(controller.page.dataset.refreshStatusUrl, { signal: controller.abort.signal });
            if (!response.ok) throw new Error("Could not read background activity.");
            const result = await response.json();
            if (progressController !== controller) return;
            controller.unavailable = false;
            renderProgress(controller.page, result);
            reportRefresh(result);
            busy = result.busy;
        }
    } catch (error) {
        if (error.name === "AbortError") return;
        // Let the independent watcher retry sooner while this card also recovers.
        controller.unavailable = true;
        controller.page.querySelector("[data-refresh-summary]").textContent = "Background status is temporarily unavailable.";
        controller.page.querySelector("[data-refresh-all]").disabled = false;
    }
    if (progressController === controller) controller.timer = setTimeout(() => pollProgress(controller), busy ? 2000 : 15000);
}

async function refreshAll(form, page) {
    const button = form.querySelector("button");
    button.disabled = true;
    page.querySelector("[data-refresh-summary]").textContent = "Queuing enabled feeds…";
    const finish = beginTask("Starting feed refresh…");
    try {
        const response = await fetch(form.action, { method: "POST", body: new FormData(form), headers: { "X-Requested-With": "XMLHttpRequest" } });
        if (!response.ok) throw new Error("Could not start refresh. Check that the server is running.");
        dismissNotice("feed-refresh");
        watchRefresh(page.dataset.refreshStatusUrl);
        // The page may have changed while the server accepted the request.
        if (progressController?.page === page) {
            cleanupProgress();
            progressController = { page, abort: new AbortController(), timer: null };
            pollProgress(progressController);
        }
    } catch (error) {
        page.querySelector("[data-refresh-summary]").textContent = error.message;
        button.disabled = false;
        notify({id: "feed-refresh", kind: "error", title: "Refresh could not start", message: error.message});
    } finally {
        finish();
    }
}

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
            dismissNotice("source-choice");
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
            notify({id: "source-choice", kind: "error", title: "Source preference could not be saved", message: `${error.message} Your previous choice is kept.`});
        }
    }
    state.running = false;
}

function initialize() {
    cleanupProgress();
    const page = document.querySelector("[data-source-settings]");
    if (!page) return;
    stateFor(page);
    const input = page.querySelector('[name="kind"]');
    updateHelp(page, input.value);
    progressController = { page, abort: new AbortController(), timer: null };
    pollProgress(progressController);
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
    document.addEventListener("world-journal:page-cleanup", cleanupProgress);
    document.addEventListener("change", event => {
        const input = event.target;
        const page = input.closest?.("[data-source-settings]");
        if (!page) return;
        if (input.matches("[data-source-health-country]")) { input.form.requestSubmit(); return; }
        if (input.name === "kind") { updateHelp(page, input.value); return; }
        if (!input.matches('[data-source-choice], [name="freshness_minutes"]')) return;
        if (input.name === "freshness_minutes" && !input.checkValidity()) {
            showStatus(page, "Choose a refresh interval of 6, 8, 10 or 12 hours.", true);
            return;
        }
        const state = stateFor(page);
        state.pending.set(input.dataset.sourceChoice || input.name, { input, value: valueOf(input) });
        savePending(page, state);
    });
    document.addEventListener("submit", event => {
        if (event.target.matches("[data-refresh-all-form]")) {
            event.preventDefault();
            event.stopImmediatePropagation();
            refreshAll(event.target, event.target.closest("[data-source-settings]"));
            return;
        }
        if (event.target.id !== "news-preferences") return;
        // Enter in the interval field must not submit all checkboxes as a batch.
        event.preventDefault();
        event.stopImmediatePropagation();
        event.target.querySelector('[name="freshness_minutes"]').dispatchEvent(new Event("change", { bubbles: true }));
    }, true);
}
