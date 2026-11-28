// One-control writes are serialized; a second click replaces its queued value.
// Saves continue across page navigation, without keeping a page listener alive.
import { beginTask, notify } from "../notifications.js";

let registered = false;
const pageStates = new WeakMap();
let progressController = null;
let sourceDialog = null;
let modalEvents = null;

function closeSourceDialog() {
    sourceDialog?.close();
    document.documentElement.classList.remove("source-modal-open");
    sourceDialog = null;
}

function showSourceDialog(dialog) {
    if (!dialog || dialog.open) return;
    sourceDialog = dialog;
    dialog.showModal();
    document.documentElement.classList.add("source-modal-open");
    dialog.querySelector('[name="location"], [name$="-location"]').focus({preventScroll: true});
}

function openSourceDialog(dialog, kind = null) {
    if (!dialog || dialog.open) return;
    const input = dialog.querySelector('[name="kind"]');
    if (kind && input.value !== kind) {
        for (const field of dialog.querySelectorAll('[name="location"], [name="name"]')) field.value = "";
        for (const error of dialog.querySelectorAll(".errorlist")) error.remove();
    }
    if (kind) input.value = kind;
    updateHelp(dialog, input.value);
    showSourceDialog(dialog);
}

function bindSourceDialog(dialog, focusOpener, signal) {
    dialog.addEventListener("close", () => {
        if (dialog.open || (sourceDialog && sourceDialog !== dialog)) return;
        document.documentElement.classList.remove("source-modal-open");
        if (sourceDialog === dialog) sourceDialog = null;
        if (dialog.isConnected) focusOpener()?.focus({preventScroll: true});
    }, {signal});
    dialog.addEventListener("click", event => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeSourceDialog();
    }, {signal});
}

function cleanupSources() {
    cleanupProgress();
    closeSourceDialog();
    document.querySelector("[data-google-pacing-dialog][open]")?.close();
    modalEvents?.abort();
    modalEvents = null;
}

function cleanupProgress() {
    if (!progressController) return;
    clearTimeout(progressController.timer);
    progressController.abort.abort();
    progressController = null;
}

function renderProgress(page, result) {
    const progress = page.querySelector("[data-refresh-progress]");
    progress.max = result.progress_max;
    progress.value = result.progress_value;
    page.querySelector("[data-refresh-summary]").textContent = result.summary;
    page.querySelector("[data-refresh-current]").textContent = result.current_label;
    page.querySelector("[data-refresh-all]").disabled = result.busy || !result.enabled;
    renderPacing(page, result.google_pacing);
    const details = page.querySelector("[data-refresh-errors]");
    details.hidden = !result.errors.length;
    page.querySelector("[data-settings-source-warning]")?.toggleAttribute("hidden", details.hidden);
    const list = details.querySelector("[data-refresh-error-list]");
    const signature = JSON.stringify(result.errors);
    if (list.dataset.errors !== signature) {
        const template = details.querySelector("[data-source-notice-template]");
        list.replaceChildren(...result.errors.map(error => {
            const item = template.content.firstElementChild.cloneNode(true);
            item.querySelector("[data-source-notice-name]").textContent = error.name;
            item.querySelector("[data-source-notice-category]").textContent = error.category;
            item.querySelector("[data-source-notice-message]").textContent = error.error;
            item.querySelector("[data-source-notice-paused]").hidden = !error.paused;
            const retry = item.querySelector("[data-source-retry]");
            retry.dataset.retryKind = error.kind;
            retry.dataset.retrySource = error.source_id;
            retry.setAttribute("aria-label", `Retry ${error.name} (${error.category})`);
            retry.disabled = error.retry_disabled;
            retry.hidden = error.paused;
            retry.textContent = error.retrying ? "Retrying…" : "Retry";
            const next = item.querySelector("[data-source-notice-time]");
            next.hidden = !error.retry_text;
            next.textContent = error.retry_text;
            return item;
        }));
        list.dataset.errors = signature;
    }
}

function renderPacing(page, pacing) {
    if (!pacing) return;
    for (const stat of page.querySelectorAll("[data-google-gap-stat]")) {
        const gap = pacing[stat.dataset.googleGapStat];
        stat.textContent = gap ? `${gap} s` : "No recorded checks";
    }
}

async function savePacing(form) {
    const button = form.querySelector('button[type="submit"]');
    if (button.disabled) return;
    button.disabled = true;
    const dialog = form.closest("dialog");
    const page = form.closest("[data-source-settings]");
    try {
        const response = await fetch(form.action, { method: "POST", body: new FormData(form) });
        const result = await response.json().catch(() => null);
        if (!response.ok || !result?.pacing) {
            notify({id: "google-pacing", kind: response.status === 400 ? "warning" : "error",
                title: "Request gaps could not be saved", message: result?.error || "Try again shortly."});
            return;
        }
        form.elements.fixed.value = result.pacing.fixed;
        form.elements.maximum.value = result.pacing.custom_maximum;
        renderPacing(page, result.pacing);
        dialog.close();
        notify({id: "google-pacing", kind: "success", title: "Google News request gaps saved"});
    } catch {
        notify({id: "google-pacing", kind: "error", title: "Request gaps could not be saved", message: "Check that the server is running."});
    } finally {
        button.disabled = false;
    }
}

function progressDelay(result) {
    if (result.busy) return 2000;
    return result.next_update_at ? Math.max(2000, Date.parse(result.next_update_at) - Date.now() + 1000) : null;
}

async function pollProgress(controller) {
    if (progressController !== controller) return;
    let delay = null;
    try {
        if (!document.hidden) {
            const response = await fetch(controller.page.dataset.refreshStatusUrl, { signal: controller.abort.signal });
            if (!response.ok) throw new Error("Could not check for news updates.");
            const result = await response.json();
            if (progressController !== controller) return;
            renderProgress(controller.page, result);
            delay = progressDelay(result);
        }
    } catch (error) {
        if (progressController !== controller || error.name === "AbortError") return;
        controller.page.querySelector("[data-refresh-summary]").textContent = "Couldn't check for updates. Try again shortly.";
        controller.page.querySelector("[data-refresh-all]").disabled = false;
        delay = 15000;
    }
    if (progressController === controller && delay !== null) controller.timer = setTimeout(() => pollProgress(controller), delay);
}

function startProgress(page, snapshot = null) {
    cleanupProgress();
    progressController = { page, abort: new AbortController(), timer: null };
    if (snapshot && !document.hidden) {
        renderProgress(page, snapshot);
        const delay = progressDelay(snapshot);
        if (delay !== null) {
            const controller = progressController;
            controller.timer = setTimeout(() => pollProgress(controller), delay);
        }
    } else pollProgress(progressController);
}

async function refreshAll(form, page) {
    const button = form.querySelector("button");
    button.disabled = true;
    page.querySelector("[data-refresh-summary]").textContent = "Starting your news update…";
    const finish = beginTask("Updating news…");
    try {
        const response = await fetch(form.action, { method: "POST", body: new FormData(form), headers: { "X-Requested-With": "XMLHttpRequest" } });
        if (!response.ok) throw new Error("Could not start refresh. Check that the server is running.");
        notify({id: "feed-refresh", kind: "success", title: "News update started", message: "You can keep reading while your news updates.", duration: 4000});
        // The page may have changed while the server accepted the request.
        if (progressController?.page === page) startProgress(page);
    } catch (error) {
        page.querySelector("[data-refresh-summary]").textContent = error.message;
        button.disabled = false;
        notify({id: "feed-refresh", kind: "error", title: "Refresh could not start", message: error.message});
    } finally {
        finish();
    }
}

async function retrySource(button, page) {
    if (button.disabled) return;
    button.disabled = true;
    button.textContent = "Retrying…";
    const body = new FormData();
    body.set("csrfmiddlewaretoken", page.querySelector('[name="csrfmiddlewaretoken"]').value);
    body.set("kind", button.dataset.retryKind);
    body.set("source_id", button.dataset.retrySource);
    const finish = beginTask("Retrying source…");
    try {
        const response = await fetch(page.dataset.sourceRetryUrl, {method: "POST", body});
        const result = await response.json();
        if (!response.ok) {
            notify({id: "feed-retry", kind: response.status === 429 || response.status === 400 ? "warning" : "error", title: "Retry could not start", message: result.error || "Try again shortly."});
        } else {
            notify({id: "feed-retry", kind: "success", title: result.queued ? "Source retry started" : "This source no longer needs a retry"});
        }
    } catch {
        notify({id: "feed-retry", kind: "error", title: "Retry could not start", message: "Check that the server is running and try again."});
    } finally {
        finish();
        button.disabled = false;
        button.textContent = "Retry";
        if (progressController?.page === page) startProgress(page);
    }
}

function valueOf(input) { return input.type === "checkbox" ? String(input.checked) : input.value; }

function stateFor(page) {
    if (!pageStates.has(page)) {
        for (const input of page.querySelectorAll('[data-source-choice], [name="freshness_minutes"], [name="archive_storage_mb"]')) {
            input.dataset.savedValue = valueOf(input);
        }
        pageStates.set(page, { pending: new Map(), running: false });
    }
    return pageStates.get(page);
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
        const interval = key === "freshness_minutes";
        const storage = key === "archive_storage_mb";
        const label = change.input.closest("label");
        const name = (label?.querySelector(".source-card-title") || label)?.textContent.trim() || "Source";
        const finish = beginTask(storage ? "Saving archive storage…" : interval ? "Saving refresh interval…" : "Saving source choice…");
        let failureKind = "error";
        try {
            const response = await fetch(page.dataset.saveUrl, { method: "POST", body, headers: { "X-Requested-With": "XMLHttpRequest" } });
            const result = await response.json().catch(() => null);
            if (!response.ok) {
                failureKind = response.status === 400 ? "warning" : "error";
                throw new Error(result?.error || "Could not save this choice. Check that the server is running and try again.");
            }
            if (!result?.states) throw new Error("The save could not be confirmed. Try again.");
            change.input.dataset.savedValue = change.value;
            for (const row of page.querySelectorAll("[data-source-row]")) {
                const saved = result.states[row.dataset.sourceRow];
                if (!saved) continue;
                row.dataset.sourceEnabled = String(saved.enabled);
            }
            document.dispatchEvent(new CustomEvent("world-journal:data-changed", { detail: { path: "/settings/news/preference/" } }));
            if (progressController?.page === page) startProgress(page);
            if (!state.pending.has(key)) notify({id: "source-choice", kind: "success", title: storage ? "Archive storage saved" : interval ? "Refresh interval saved" : `${name} ${change.value === "true" ? "enabled" : "disabled"}`});
        } catch (error) {
            if (!state.pending.has(key) && valueOf(change.input) === change.value) {
                if (change.input.type === "checkbox") change.input.checked = change.input.dataset.savedValue === "true";
                else change.input.value = change.input.dataset.savedValue;
                change.input.dispatchEvent(new Event("change"));
            }
            notify({id: "source-choice", kind: failureKind, title: storage ? "Archive storage could not be saved" : interval ? "Refresh interval could not be saved" : "Source choice could not be saved", message: `${error.message} Your last confirmed choice is shown.`});
        } finally {
            finish();
        }
    }
    state.running = false;
}

function initialize() {
    const page = document.querySelector("[data-source-settings]");
    if (!page) { cleanupSources(); return; }
    modalEvents?.abort();
    modalEvents = new AbortController();
    stateFor(page);
    const dialog = page.querySelector("[data-source-modal]");
    updateHelp(dialog, dialog.querySelector('[name="kind"]').value);
    bindSourceDialog(dialog, () => {
        const kind = dialog.querySelector('[name="kind"]').value === "youtube" ? "youtube" : "rss";
        return page.querySelector(`[data-source-modal-open="${kind}"]`);
    }, modalEvents.signal);
    for (const feedDialog of page.querySelectorAll("[data-source-feed-modal]")) {
        bindSourceDialog(feedDialog, () => page.querySelector(`[data-source-feed-open][aria-controls="${feedDialog.id}"]`), modalEvents.signal);
    }
    const invalidFeed = page.querySelector('[data-source-feed-modal][data-open-on-load="true"]');
    if (invalidFeed) {
        invalidFeed.dataset.openOnLoad = "false";
        showSourceDialog(invalidFeed);
    } else if (dialog.dataset.openOnLoad === "true") {
        dialog.dataset.openOnLoad = "false";
        openSourceDialog(dialog);
    }
    const snapshot = page.querySelector("#source-refresh-snapshot");
    startProgress(page, snapshot ? JSON.parse(snapshot.textContent) : null);
    snapshot?.remove();
}

function updateHelp(dialog, kind) {
    const youtube = kind === "youtube";
    dialog.querySelector("#add-source-title").textContent = youtube ? "Add a YouTube channel" : "Add a news source";
    dialog.querySelector("[data-custom-source-help]").textContent = youtube
        ? "Paste a YouTube channel link or @handle."
        : "Paste the website’s news feed link.";
    dialog.querySelector('[name="location"]').placeholder = youtube ? "YouTube channel link or @handle" : "https://example.com/news.xml";
}

export function registerSourceSettings() {
    if (registered) return;
    registered = true;
    document.addEventListener("world-journal:page-ready", initialize);
    document.addEventListener("world-journal:page-cleanup", cleanupSources);
    document.addEventListener("click", event => {
        const retry = event.target.closest("[data-source-retry]");
        if (retry) retrySource(retry, retry.closest("[data-source-settings]"));
        const opener = event.target.closest("[data-source-modal-open]");
        if (opener) openSourceDialog(opener.closest("[data-source-settings]").querySelector("[data-source-modal]"), opener.dataset.sourceModalOpen);
        const feedOpener = event.target.closest("[data-source-feed-open]");
        if (feedOpener) showSourceDialog(document.getElementById(feedOpener.getAttribute("aria-controls")));
        if (event.target.closest("[data-source-modal-close]")) closeSourceDialog();
        const pacingOpener = event.target.closest("[data-google-pacing-open]");
        if (pacingOpener) pacingOpener.closest("[data-source-settings]").querySelector("[data-google-pacing-dialog]").showModal();
        event.target.closest("[data-google-pacing-close]")?.closest("dialog").close();
    });
    document.addEventListener("visibilitychange", () => {
        const page = document.querySelector("[data-source-settings]");
        if (!page) return;
        if (document.hidden) cleanupProgress();
        else startProgress(page);
    });
    document.addEventListener("change", event => {
        const input = event.target;
        const page = input.closest?.("[data-source-settings]");
        if (!page) return;
        if (!input.matches('[data-source-choice], [name="freshness_minutes"], [name="archive_storage_mb"]')) return;
        if (input.name === "freshness_minutes" && !input.checkValidity()) {
            notify({id: "source-choice", kind: "warning", title: "Choose a refresh interval", message: "Choose 2, 4, 6, 8, 10 or 12 hours."});
            return;
        }
        const state = stateFor(page);
        state.pending.set(input.dataset.sourceChoice || input.name, { input, value: valueOf(input) });
        savePending(page, state);
    });
    document.addEventListener("submit", event => {
        if (event.target.matches("[data-google-pacing-form]")) {
            event.preventDefault();
            event.stopImmediatePropagation();
            savePacing(event.target);
            return;
        }
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
        const preference = document.activeElement?.closest(".settings-field")?.querySelector("select") || event.target.querySelector('[name="freshness_minutes"]');
        preference.dispatchEvent(new Event("change", { bubbles: true }));
    }, true);
}
