// Retain rendered drawers independently of page swaps. This cache contains HTML,
// not live DOM nodes: video thumbnails and players are mounted only on demand.
const entries = new Map();
let started = false;
let invalidatedAt = 0;
const MAX_AGE_MS = 5 * 60 * 1000;

export function getCountryFeed(code, kind) {
    const entry = entries.get(`${kind}:${code}`);
    return entry && !entry.pending && Date.now() - entry.requestedAt < MAX_AGE_MS ? entry : null;
}

export function rememberCountryFeed(code, kind, markup, { requestedAt = Date.now(), notify = true } = {}) {
    const selector = kind === "articles" ? "[data-country-news-result]" : "[data-country-videos-result]";
    const fragment = document.createElement("template");
    fragment.innerHTML = markup;
    const root = fragment.content.querySelector(selector);
    const returnedCode = kind === "articles" ? root?.dataset.newsCountry : root?.dataset.videoCountry;
    if (returnedCode !== code) throw new Error("Incorrect country feed response");
    const key = `${kind}:${code}`;
    const previous = entries.get(key);
    if (requestedAt < invalidatedAt) return previous || null;
    if (previous && previous.requestedAt > requestedAt) return previous;
    const entry = { markup, requestedAt, pending: root.dataset.feedPending === "true" };
    entries.set(key, entry);
    if (notify && previous?.markup !== markup) {
        document.dispatchEvent(new CustomEvent("world-journal:feed-cache-changed", { detail: { code, kind, entry } }));
    }
    return entry;
}

export function initializeNewsCache() {
    if (started) return;
    started = true;
    document.addEventListener("world-journal:data-changed", event => {
        const path = event.detail?.path || "";
        if (!path.startsWith("/settings/news/") && !path.startsWith("/settings/backups/")) return;
        invalidatedAt = Date.now();
        entries.clear();
    });
}
