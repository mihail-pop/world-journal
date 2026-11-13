import { notify, dismissNotice } from "./notifications.js";

let confirmed = null;
let pending = {};
let inFlight = null;
let pendingNotice = false;
let refreshRequest = null;
let initialized = false;

export function readAppPreferences() {
    confirmed ??= JSON.parse(document.querySelector("#app-preferences").textContent);
    return {...confirmed, ...inFlight, ...pending};
}

function publish() {
    const values = readAppPreferences();
    const root = document.documentElement;
    if (root.dataset.theme !== values.theme) {
        root.dataset.theme = values.theme;
        document.dispatchEvent(new CustomEvent("world-journal:theme-change", {detail: {theme: values.theme}}));
    }
    if (root.dataset.font !== values.font) {
        root.dataset.font = values.font;
        document.dispatchEvent(new CustomEvent("world-journal:font-change", {detail: {font: values.font}}));
    }
    document.dispatchEvent(new CustomEvent("world-journal:app-preferences-change", {detail: values}));
}

export function acceptAppPreferences(snapshot) {
    readAppPreferences();
    if (!snapshot || !Number.isSafeInteger(snapshot.revision) || snapshot.revision < confirmed.revision) return false;
    // HTMX events also carry their source element; retain only preference keys.
    for (const key of Object.keys(confirmed)) {
        if (Object.hasOwn(snapshot, key)) confirmed[key] = snapshot[key];
    }
    publish();
    return true;
}

async function flush() {
    if (inFlight) return;
    let savedNotice = false;
    while (Object.keys(pending).length) {
        inFlight = pending;
        pending = {};
        const notifySaved = pendingNotice;
        pendingNotice = false;
        try {
            const response = await fetch(document.body.dataset.preferencesUrl, {
                method: "POST", keepalive: true,
                headers: {"Content-Type": "application/json", "Accept": "application/json", "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content},
                body: JSON.stringify(inFlight),
            });
            if (!response.ok) throw new Error("Preferences could not be saved");
            const snapshot = await response.json();
            if (!Number.isSafeInteger(snapshot?.revision)) throw new Error("Invalid Preferences response");
            inFlight = null;
            if (!acceptAppPreferences(snapshot)) publish();
            savedNotice ||= notifySaved;
        } catch {
            inFlight = null;
            publish();
            savedNotice = false;
            notify({id: "preferences-save-error", kind: "error", title: "Preferences could not be saved", message: "Your last confirmed choices are shown. Try again when the server is available."});
        }
    }
    if (savedNotice) {
        dismissNotice("preferences-save-error");
        document.dispatchEvent(new CustomEvent("world-journal:preferences-saved"));
    }
}

export function writeAppPreferences(patch, {notifySaved = false} = {}) {
    const current = readAppPreferences();
    for (const [key, value] of Object.entries(patch)) {
        if (key !== "revision" && Object.hasOwn(current, key) && value !== current[key]) pending[key] = value;
    }
    if (!Object.keys(pending).length) return current;
    pendingNotice ||= notifySaved;
    publish();
    queueMicrotask(flush);
    return readAppPreferences();
}

async function refresh() {
    if (refreshRequest || document.visibilityState === "hidden") return;
    refreshRequest = fetch(document.body.dataset.preferencesUrl, {cache: "no-store", headers: {Accept: "application/json"}});
    try {
        const response = await refreshRequest;
        if (response.ok) acceptAppPreferences(await response.json());
    } catch {
        // A background refresh must not discard usable saved or pending choices.
    } finally {
        refreshRequest = null;
    }
}

export function initializeAppPreferences() {
    if (initialized) return;
    initialized = true;
    publish();
    document.addEventListener("world-journal:app-preferences-loaded", event => acceptAppPreferences(event.detail));
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
}
