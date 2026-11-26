// Shared bookmark actions for country drawers and News cards.
import { beginTask, notify } from "./notifications.js";
const saved = new Map();
const pending = new Map();
const checking = new Set();
const changes = new Map();
let registered = false;
let revision = 0;
let statusQueued = false;

function identity(url) {
    const params = new URL(url, location.origin).searchParams;
    return params.get("type") === "youtube" ? `video:${params.get("video")}` : `article:${params.get("url")}`;
}

function wrappers() { return document.querySelectorAll(".journal-bookmark-actions"); }

function renderedState(link) {
    return link.dataset.savedEntry ? {entry_id: link.dataset.savedEntry, edit_url: link.dataset.savedEditUrl, delete_url: link.dataset.savedDeleteUrl} : null;
}

function sync(wrapper) {
    const link = wrapper.querySelector("[data-bookmark-url]");
    if (!link) return;
    const key = identity(link.dataset.bookmarkUrl);
    const result = saved.has(key) ? saved.get(key) : renderedState(link);
    const button = wrapper.querySelector("[data-journal-quick-save]");
    button.title = "Quick Save";
    button.setAttribute("aria-label", "Quick Save");
    const busy = pending.has(key);
    button.hidden = Boolean(result);
    button.disabled = busy;
    button.setAttribute("aria-busy", String(busy));
    link.setAttribute("aria-busy", String(busy));
    link.setAttribute("aria-disabled", String(busy));
    link.classList.toggle("is-saved", Boolean(result));
    link.removeAttribute("title");
    if (result) {
        link.setAttribute("role", "button");
        link.setAttribute("aria-label", "Remove from Journal");
    } else {
        link.removeAttribute("role");
        link.removeAttribute("aria-label");
    }
    if (link.dataset.bookmarkState !== String(Boolean(result))) {
        const icon = document.querySelector(`[data-control-icon="${result ? "check" : "bookmark"}"]`).content.cloneNode(true);
        link.replaceChildren(icon, document.createTextNode(result ? " Saved" : " Save"));
        link.dataset.bookmarkState = String(Boolean(result));
    }
    const href = result?.edit_url || link.dataset.bookmarkUrl;
    const boosted = result ? "false" : "true";
    if (link.getAttribute("href") !== href || link.getAttribute("hx-boost") !== boosted || link.hasAttribute("hx-get")) {
        link.href = href;
        link.setAttribute("hx-boost", boosted);
        link.removeAttribute("hx-get");
        window.htmx.process(link);
    }
    link.dataset.savedEntry = result?.entry_id || "";
    link.dataset.savedEditUrl = result?.edit_url || "";
    link.dataset.savedDeleteUrl = result?.delete_url || "";
}

function refresh() { for (const wrapper of wrappers()) sync(wrapper); }

function checkStatus() {
    if (statusQueued || !document.body.dataset.journalBookmarkStatusUrl) return;
    statusQueued = true;
    queueMicrotask(() => {
        statusQueued = false;
        const links = new Map();
        for (const wrapper of wrappers()) {
            const link = wrapper.querySelector("[data-bookmark-url]");
            const key = identity(link.dataset.bookmarkUrl);
            if (!saved.has(key) && !pending.has(key) && !checking.has(key)) links.set(key, link.dataset.bookmarkUrl);
        }
        const entries = [...links];
        for (let index = 0; index < entries.length; index += 100) void readStatus(entries.slice(index, index + 100));
    });
}

async function readStatus(entries) {
    const version = revision;
    const versions = new Map(entries.map(([key]) => [key, changes.get(key) || 0]));
    const body = new URLSearchParams();
    for (const [key, url] of entries) {
        checking.add(key);
        const params = new URL(url).searchParams;
        const field = key.startsWith("video:") ? "video" : "url";
        body.append(field, params.get(field));
    }
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 15000);
    try {
        const response = await fetch(document.body.dataset.journalBookmarkStatusUrl, {method: "POST", body, signal: abort.signal,
            headers: {"Accept": "application/json", "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content}});
        if (!response.ok) return;
        const result = await response.json();
        if (version !== revision) return;
        for (const [key] of entries) {
            if (!pending.has(key) && (changes.get(key) || 0) === versions.get(key)) saved.set(key, result.bookmarks[key] || null);
        }
        refresh();
    } catch { /* Keep the rendered state; a later visit can check again. */ }
    finally {
        clearTimeout(timeout);
        for (const [key] of entries) checking.delete(key);
        if (version !== revision) checkStatus();
    }
}

function enhance(root) {
    for (const link of root.querySelectorAll("a[href]")) {
        if (link.id === "mp-info") continue;
        const url = new URL(link.dataset.bookmarkUrl || link.href, location.origin);
        if (url.origin !== location.origin || url.pathname !== document.body.dataset.journalNewUrl
            || !["article", "youtube"].includes(url.searchParams.get("type"))) continue;
        if (!link.parentElement.matches(".journal-bookmark-actions")) {
            const wrapper = document.createElement("span");
            wrapper.className = "journal-bookmark-actions";
            link.before(wrapper);
            wrapper.append(link);
        }
        const wrapper = link.parentElement;
        if (!wrapper.querySelector("[data-journal-quick-save]")) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "journal-quick-save";
            button.dataset.journalQuickSave = "";
            button.title = "Quick Save";
            button.setAttribute("aria-label", button.title);
            button.append(document.querySelector('[data-control-icon="plus-small"]').content.cloneNode(true));
            wrapper.append(button);
        }
        link.dataset.bookmarkUrl = url.href;
        const key = identity(url.href);
        if (!link.hasAttribute("data-bookmark-initialized")) {
            if (!saved.has(key) && link.hasAttribute("data-bookmark-checked")) saved.set(key, renderedState(link));
            link.dataset.bookmarkInitialized = "";
        }
        sync(wrapper);
    }
    checkStatus();
}

async function changeBookmark(link, remove = false) {
    const originalUrl = link.dataset.bookmarkUrl;
    const key = identity(originalUrl);
    if (pending.has(key)) return;
    const bookmark = saved.get(key) || renderedState(link);
    if (remove && !bookmark || !remove && bookmark) return;
    changes.set(key, (changes.get(key) || 0) + 1);
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 20000);
    const finish = beginTask(remove ? "Removing from Journal…" : "Saving to Journal…");
    const path = remove ? bookmark.delete_url : document.body.dataset.journalQuickSaveUrl;
    const task = (async () => {
        try {
            const response = await fetch(path, {method: "POST", signal: abort.signal,
                body: remove ? new URLSearchParams({confirm: "on"}) : new URL(originalUrl).searchParams,
                headers: {"Accept": "application/json", "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content}});
            const result = response.headers.get("Content-Type")?.includes("application/json") ? await response.json() : {};
            if (!response.ok && !(remove && response.status === 404)) throw new Error(result.message || "Try again.");
            if (remove && response.status === 404) saved.delete(key);
            else saved.set(key, remove ? result.bookmarks[key] || null : result);
            notify({id: "journal-bookmark", kind: remove || result.created ? "success" : "info",
                title: remove ? "Removed from Journal" : result.created ? "Saved to Journal" : "Already saved in Journal",
                ...(!remove ? {action: {label: "Open entry", href: result.edit_url}} : {})});
            document.dispatchEvent(new CustomEvent("world-journal:data-changed", {detail: {path, bookmarkChanged: true, deletedEntryId: remove ? bookmark.entry_id : undefined}}));
        } catch (error) {
            notify({id: "journal-bookmark", kind: "error", title: remove ? "Could not remove from Journal" : "Could not save to Journal",
                message: error.name === "AbortError" ? "The request timed out. You can retry safely." : error.message});
        } finally {
            clearTimeout(timeout);
            finish();
            pending.delete(key);
            refresh();
            checkStatus();
        }
    })();
    pending.set(key, task);
    refresh();
    await task;
}

export function registerJournalBookmarks() {
    if (registered) return;
    registered = true;
    enhance(document);
    document.addEventListener("world-journal:page-ready", () => enhance(document));
    document.addEventListener("world-journal:data-changed", event => {
        if (!event.detail?.path?.startsWith("/journal/") || event.detail.bookmarkChanged) return;
        revision += 1;
        saved.clear();
        checkStatus();
    });
    document.addEventListener("keydown", event => {
        if (event.key === " " && event.target.matches('[data-bookmark-url][role="button"]')) {
            event.preventDefault();
            event.target.click();
        }
    });
    document.addEventListener("click", event => {
        const button = event.target.closest("[data-journal-quick-save]");
        const link = button ? button.parentElement.querySelector("[data-bookmark-url]") : event.target.closest("[data-bookmark-url]");
        if (!link) return;
        const key = identity(link.dataset.bookmarkUrl);
        const result = saved.has(key) ? saved.get(key) : renderedState(link);
        if (button || result || pending.has(key)) {
            event.preventDefault();
            event.stopImmediatePropagation();
            if (!pending.has(key)) void changeBookmark(link, Boolean(result));
        }
    }, true);
    new MutationObserver(records => {
        if (records.some(record => [...record.addedNodes].some(node => node.nodeType === Node.ELEMENT_NODE
            && (node.matches("a[href]") || node.querySelector("a[href]"))))) enhance(document);
    }).observe(document.querySelector("#app-content"), {childList: true, subtree: true});
}
