import { dismissNotice, notify } from "../notifications.js";
import { randomId } from "../random_id.js";

const editors = new Map();
const replayLinks = new WeakSet();
let registered = false;

function showStatus(state, message, status) {
    const output = state.form.querySelector("[data-autosave-status]");
    const text = output.querySelector("[data-autosave-message]");
    if (text) text.textContent = message;
    else output.textContent = message;
    output.title = message;
    output.setAttribute("aria-label", message);
    output.dataset.saveState = status;
    clearTimeout(state.statusTimer);
    if (status === "saved") state.statusTimer = setTimeout(() => {
        if (output.dataset.saveState === "saved") showStatus(state, "Autosave on · all changes saved", "idle");
    }, 1000);
}

function trackEditor(form) {
    if (editors.has(form)) return editors.get(form);
    const hasPrefill = form.getAttribute("action") === "/journal/new/" && ["title", "body", "source_url"].some(name => form.elements.namedItem(name)?.value.trim());
    const state = {form, version: hasPrefill || form.querySelector("[data-autosave-retry]") ? 1 : 0, savedVersion: 0, pending: null};
    editors.set(form, state);
    if (state.version) showStatus(state, "Unsaved changes", "dirty");
    for (const name of ["input", "change", "world-journal:editor-changed"]) {
        form.addEventListener(name, event => {
            if (event.target.closest?.("[data-journal-ui]")) return;
            if (state.applying) return;
            state.version += 1;
            if (!state.pending) showStatus(state, "Unsaved changes", "dirty");
        });
    }
    return state;
}

async function save(state, explicit = false, skipUploads = false) {
    if (state.form.dataset.journalDeleted) return false;
    try {
        await state.form.journalReady;
        if (!skipUploads) await Promise.all(state.form.journalPendingUploads || []);
    } catch {
        showStatus(state, "The editor could not be opened. Reload this page before saving.", "error");
        return false;
    }
    if (state.form.dataset.journalDeleted) return false;
    if (state.pending) {
        if (!await state.pending) return false;
        if (state.savedVersion === state.version) return true;
        return save(state, explicit, skipUploads);
    }
    if (state.savedVersion === state.version && !explicit) return true;
    const {form} = state;
    const retrying = Boolean(state.retry);
    if (!state.retry) {
        form.dispatchEvent(new CustomEvent("world-journal:prepare-save", {bubbles: true}));
        const data = new FormData(form);
        data.set("save_attempt", randomId());
        state.retry = {data, version: state.version};
    }
    const {data, version} = state.retry;
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 20000);
    showStatus(state, "Saving…", "saving");
    state.pending = (async () => {
        try {
            const response = await fetch(form.dataset.autosaveUrl, {
                method: "POST", body: data, signal: abort.signal,
                headers: {"Accept": "application/json", "X-CSRFToken": data.get("csrfmiddlewaretoken")},
            });
            const result = response.headers.get("Content-Type")?.includes("application/json") ? await response.json() : {message: "Not saved: the server could not complete the request. Try again."};
            if (!response.ok || typeof result.revision !== "string") {
                if (response.status >= 400 && response.status < 500) state.retry = null;
                state.conflicted = response.status === 409;
                form.dispatchEvent(new CustomEvent("world-journal:validation-errors", {bubbles: true, detail: {errors: result.errors, focus: explicit}}));
                throw new Error(result.message || "Could not save. Try Save again.");
            }
            form.dispatchEvent(new CustomEvent("world-journal:validation-errors", {bubbles: true, detail: {errors: {}}}));
            form.action = result.edit_url;
            form.elements.namedItem("entry_revision").value = result.revision;
            if (form.isConnected) {
                history.replaceState(history.state, "", result.edit_url);
                document.dispatchEvent(new CustomEvent("world-journal:location-change"));
            }
            document.dispatchEvent(new CustomEvent("world-journal:journal-autosaved", {detail: {form, url: result.edit_url}}));
            // Only fill server defaults when the corresponding input has not
            // changed while saving. Never replace the body or rebuild its DOM.
            const reader = form.querySelector("[data-journal-reader]");
            if (reader) { reader.href = result.read_url; reader.hidden = false; }
            for (const [prefix, section] of Object.entries(result.sections)) {
                const id = form.elements.namedItem(prefix + "-id");
                if (id) id.value = section.id;
                const title = form.elements.namedItem(prefix + "-title");
                if (title && !title.value.trim() && !String(data.get(prefix + "-title") || "").trim()) {
                    title.value = section.title;
                    const caption = title.closest("[data-journal-section]")?.querySelector("[data-section-caption]");
                    if (caption) caption.textContent = section.title;
                }
            }
            for (const card of form.querySelectorAll("[data-journal-section]")) {
                const prefix = card.dataset.editorPage;
                if (!data.get(prefix + "-DELETE")) continue;
                if (card.querySelector('[name$="-DELETE"]').checked) card.remove();
                else card.querySelector('[name$="-id"]').value = "";
            }
            form.dispatchEvent(new CustomEvent("world-journal:sections-saved", {bubbles: true}));
            const countries = form.elements.namedItem("countries");
            const selected = [...countries.selectedOptions].map(option => option.value).sort();
            if (JSON.stringify(selected) === JSON.stringify(data.getAll("countries").sort())) {
                state.applying = true;
                for (const option of countries.options) option.selected = result.countries.includes(option.value);
                countries.dispatchEvent(new Event("change", {bubbles: true}));
                state.applying = false;
            }
            state.savedVersion = version;
            state.retry = null;
            state.conflicted = false;
            dismissNotice(`autosave-${form.dataset.autosaveUrl}`);
            showStatus(state, state.version === version ? "Saved" : "Unsaved changes", state.version === version ? "saved" : "dirty");
            document.dispatchEvent(new CustomEvent("world-journal:data-changed", {detail: {path: result.edit_url}}));
            return true;
        } catch (error) {
            showStatus(state, error.name === "AbortError" ? "Not saved: connection timed out. Try again." : error.message || "Not saved: connection unavailable.", "error");
            notify({id: `autosave-${form.dataset.autosaveUrl}`, kind: "error", title: "Your changes need saving", message: `${form.querySelector('[data-autosave-status]').textContent} Your draft is kept in this tab.`, ...(!state.conflicted ? {action: {label: "Retry save", run: () => { if (editors.has(form)) void save(state, true); }}} : {})});
            return false;
        } finally {
            clearTimeout(timeout);
            state.pending = null;
        }
    })();
    const saved = await state.pending;
    return saved && retrying && state.savedVersion !== state.version ? save(state, explicit, skipUploads) : saved;
}

export function saveJournalEditor(form, {skipUploads = false} = {}) {
    return save(trackEditor(form), new URL(form.action, location.href).pathname === "/journal/new/", skipUploads);
}

export function registerJournalAutosave() {
    if (registered) return;
    registered = true;
    document.addEventListener("world-journal:data-changed", event => {
        const removed = event.detail?.deletedEntryId;
        if (!removed) return;
        for (const [form, state] of editors) {
            if (form.elements.namedItem("entry_id")?.value !== removed) continue;
            form.dataset.journalDeleted = "true";
            clearTimeout(state.statusTimer);
            dismissNotice(`autosave-${form.dataset.autosaveUrl}`);
            editors.delete(form);
        }
    });
    document.addEventListener("world-journal:page-ready", () => {
        const form = document.querySelector("[data-journal-editor]");
        if (document.querySelector('#app-content > [data-page="journal"]')) {
            for (const [previous, state] of editors) {
                if (previous === form) continue;
                const forget = () => {
                    if (previous.isConnected || state.pending || state.savedVersion !== state.version) return;
                    clearTimeout(state.statusTimer);
                    dismissNotice(`autosave-${previous.dataset.autosaveUrl}`);
                    editors.delete(previous);
                };
                // History or a server redirect can replace a detached editor
                // without passing through the link guard. Confirm its save first.
                if (state.pending || state.savedVersion !== state.version) void save(state).then(forget);
                else forget();
            }
        }
        if (form) trackEditor(form);
    });
    // The timer only saves the visible editor. Leaving Journal flushes its draft.
    setInterval(() => {
        for (const state of editors.values()) if (state.form.isConnected && !state.pending && !state.submitting && !state.conflicted && state.version !== state.savedVersion) void save(state);
    }, 60000);
    document.addEventListener("click", async event => {
        const link = event.target.closest("a[href]");
        if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.target === "_blank" || link.hasAttribute("download")) return;
        if (replayLinks.has(link)) { replayLinks.delete(link); return; }
        const visibleForm = document.querySelector("[data-journal-editor]");
        const state = visibleForm ? trackEditor(visibleForm) : [...editors.values()].find(item => !item.form.isConnected);
        const form = state?.form;
        const url = new URL(link.href, location.href);
        // In-Journal navigation replaces the editor; section switching retains
        // it. Save before replacing, including a second click on Journal.
        if (!form || url.origin !== location.origin || !url.pathname.startsWith("/journal/") || link.getAttribute("href").startsWith("#")) return;
        // Returning to a retained editor preserves its unsaved draft directly.
        // Replacing it with another Journal screen must flush it first, even
        // when the editor is currently detached behind Map or Settings.
        if (!visibleForm && url.pathname === new URL(form.action, location.href).pathname) return;
        if (state.savedVersion === state.version && !state.pending) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        if (state.navigating) return;
        state.navigating = true;
        const outgoingPage = document.querySelector("#app-content > [data-page]");
        link.setAttribute("aria-busy", "true");
        try {
            if (await save(state) && outgoingPage?.isConnected && link.isConnected) {
                replayLinks.add(link);
                link.click();
            }
        } finally {
            state.navigating = false;
            link.removeAttribute("aria-busy");
        }
    }, true);
    document.addEventListener("submit", async event => {
        const form = event.target.closest("[data-journal-editor]");
        if (!form || event.submitter?.value === "add_section") return;
        event.preventDefault();
        event.stopImmediatePropagation();
        const state = trackEditor(form);
        if (state.submitting) return;
        state.submitting = true;
        const button = form.querySelector("[data-journal-save]");
        if (button) button.disabled = true;
        try { await save(state, true); }
        finally { state.submitting = false; if (button) button.disabled = false; }
    }, true);
    document.body.addEventListener("htmx:afterRequest", event => {
        const state = editors.get(event.detail.elt);
        if (state && !event.detail.successful) {
            state.submitting = false;
            showStatus(state, "Not saved: connection unavailable. Try again.", "error");
        }
    });
    document.body.addEventListener("htmx:configRequest", event => {
        const form = event.detail.elt?.closest("[data-journal-editor]");
        // Boosted forms may have captured their original action on processing.
        // Read the updated URL after autosave instead of posting to /new/.
        if (form && event.detail.verb === "post") event.detail.path = form.getAttribute("action");
    });
    document.addEventListener("world-journal:page-cleanup", event => {
        if (event.detail?.page !== "journal") return;
        const form = document.querySelector("[data-journal-editor]");
        const state = editors.get(form);
        const forget = () => {
            if (!form || event.detail.preserveJournal) return;
            clearTimeout(state?.statusTimer);
            editors.delete(form);
            dismissNotice(`autosave-${form.dataset.autosaveUrl}`);
        };
        if (state && (state.pending || state.version !== state.savedVersion)) {
            void save(state).then(saved => { if (saved) forget(); });
        } else forget();
    });
    window.addEventListener("beforeunload", event => {
        if (![...editors.values()].some(state => state.pending || state.version !== state.savedVersion)) return;
        event.preventDefault();
        event.returnValue = "";
    });
}
