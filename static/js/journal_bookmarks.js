// One bookmark interaction for country drawers, News cards and the shell player.
const saved = new Map();
const pending = new Map();
let registered = false;
let noticeTimer;

function identity(url) {
    const params = new URL(url, location.origin).searchParams;
    return params.get("type") === "youtube" ? `video:${params.get("video")}` : `article:${params.get("url")}`;
}

function showNotice(message, error = false) {
    const notice = document.querySelector("[data-quick-save-notice]");
    clearTimeout(noticeTimer);
    notice.textContent = message;
    notice.classList.toggle("is-error", error);
    notice.hidden = false;
    noticeTimer = setTimeout(() => { notice.hidden = true; }, error ? 8000 : 3500);
}

function sync(wrapper) {
    const link = wrapper.querySelector("[data-bookmark-url]");
    if (!link) return;
    const key = identity(link.dataset.bookmarkUrl);
    const result = saved.get(key);
    const button = wrapper.querySelector("[data-journal-quick-save]");
    const busy = pending.has(key);
    button.disabled = busy || Boolean(result);
    button.title = result ? "Saved to Journal" : busy ? "Saving…" : "Quick save to Journal";
    button.setAttribute("aria-label", button.title);
    button.setAttribute("aria-busy", String(busy));
    button.classList.toggle("is-saved", Boolean(result));
    button.replaceChildren(document.querySelector(`[data-control-icon="${result ? "check" : "plus"}"]`).content.cloneNode(true));
    if (result && link.getAttribute("href") !== result.edit_url) {
        link.href = result.edit_url;
        link.setAttribute("hx-get", result.edit_url);
        window.htmx.process(link);
    } else if (!result && link.hasAttribute("hx-get")) {
        link.href = link.dataset.bookmarkUrl;
        link.removeAttribute("hx-get");
        window.htmx.process(link);
    }
}

function enhance(root) {
    for (const link of root.querySelectorAll("a[href]")) {
        const url = new URL(link.dataset.bookmarkUrl || link.href, location.origin);
        if (url.origin !== location.origin || url.pathname !== document.body.dataset.journalNewUrl
            || !["article", "youtube"].includes(url.searchParams.get("type"))) {
            if (link.parentElement.matches(".journal-bookmark-actions")) link.parentElement.querySelector("[data-journal-quick-save]").hidden = true;
            continue;
        }
        if (!link.parentElement.matches(".journal-bookmark-actions")) {
            const wrapper = document.createElement("span");
            wrapper.className = "journal-bookmark-actions";
            link.before(wrapper);
            wrapper.append(link);
            const button = document.createElement("button");
            button.type = "button";
            button.className = "journal-quick-save";
            button.dataset.journalQuickSave = "";
            wrapper.append(button);
        }
        link.dataset.bookmarkUrl = url.href;
        link.parentElement.querySelector("[data-journal-quick-save]").hidden = false;
        sync(link.parentElement);
    }
}

function refresh() {
    for (const wrapper of document.querySelectorAll(".journal-bookmark-actions")) sync(wrapper);
}

async function quickSave(link) {
    const originalUrl = link.dataset.bookmarkUrl;
    const key = identity(originalUrl);
    if (pending.has(key) || saved.has(key)) return;
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 20000);
    const task = (async () => {
        try {
            const response = await fetch(document.body.dataset.journalQuickSaveUrl, {
                method: "POST", body: new URL(originalUrl).searchParams, signal: abort.signal,
                headers: {"Accept": "application/json", "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content},
            });
            const result = response.headers.get("Content-Type")?.includes("application/json") ? await response.json() : {};
            if (!response.ok) throw new Error(result.message || "Could not save. Try again.");
            saved.set(key, result);
            showNotice(result.created ? "Saved to Journal" : "Already saved in Journal");
            document.dispatchEvent(new CustomEvent("world-journal:data-changed", {detail: {path: document.body.dataset.journalQuickSaveUrl}}));
        } catch (error) {
            showNotice(error.name === "AbortError" ? "Saving timed out. You can retry safely." : error.message, true);
        } finally {
            clearTimeout(timeout);
            pending.delete(key);
            refresh();
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
    document.addEventListener("world-journal:player-bookmark-changed", () => enhance(document));
    document.addEventListener("world-journal:data-changed", event => {
        if (!event.detail?.path?.startsWith("/journal/") || !event.detail.path.endsWith("/delete/")) return;
        saved.clear();
        refresh();
    });
    document.addEventListener("click", event => {
        const button = event.target.closest("[data-journal-quick-save]");
        if (!button) return;
        event.preventDefault();
        const link = button.parentElement.querySelector("[data-bookmark-url]");
        if (link) quickSave(link);
    });
    new MutationObserver(records => {
        // Feed updates can insert cards without swapping the whole page.
        if (records.some(record => [...record.addedNodes].some(node => node.nodeType === Node.ELEMENT_NODE
            && (node.matches("a[href]") || node.querySelector("a[href]"))))) enhance(document);
    }).observe(document.querySelector("#app-content"), {childList: true, subtree: true});
}
