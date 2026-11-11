// Retain rendered drawers independently of page swaps. This cache contains HTML,
// not live DOM nodes: video thumbnails and players are mounted only on demand.
const entries = new Map();
const versions = new Map();
let generation = 0;
let drawerPage = null;
let priorityCountry = null;
let timer = null;
let running = false;
let started = false;
let endpoint;
let invalidatedAt = 0;

export function getCountryFeed(code, kind) {
    return entries.get(`${kind}:${code}`);
}

export function rememberCountryFeed(code, kind, markup, { requestedAt = Date.now(), version = "", notify = true } = {}) {
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
    const entry = { markup, version, requestedAt, pending: root.dataset.feedPending === "true" };
    entries.set(key, entry);
    if (notify && previous?.markup !== markup) {
        document.dispatchEvent(new CustomEvent("world-journal:feed-cache-changed", { detail: { code, kind, entry } }));
    }
    return entry;
}

export function prioritizeCountryFeed(code) {
    priorityCountry = code;
    schedule(0);
}

function visibleCountry() {
    if (drawerPage === "map") {
        return document.querySelector("[data-country-drawer]:not([hidden])")?.dataset.countryCode;
    }
    if (drawerPage === "countries") {
        const directory = document.querySelector("[data-country-directory]");
        if (["articles", "videos"].includes(directory?.dataset.selectedTab)) return directory.dataset.selectedCountry;
    }
    return null;
}

function schedule(delay) {
    clearTimeout(timer);
    if (drawerPage && !document.hidden) timer = setTimeout(poll, delay);
}

async function readBatch(codes, currentGeneration, priority = null) {
    const url = new URL(endpoint, location.origin);
    if (codes.length) {
        url.searchParams.set("countries", codes.join(","));
        url.searchParams.set("versions", codes.map(code => versions.get(code) || "").join(","));
    }
    if (priority) url.searchParams.set("priority", priority);
    const requestedAt = Date.now();
    const response = await fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
    if (!response.ok) throw new Error("Feed cache is temporarily unavailable");
    const result = await response.json();
    if (generation !== currentGeneration) return null;
    for (const [code, record] of Object.entries(result.records)) {
        rememberCountryFeed(code, "articles", record.articles, { requestedAt, version: record.version });
        rememberCountryFeed(code, "videos", record.videos, { requestedAt, version: record.version });
        versions.set(code, record.version);
    }
    return result.warming;
}

async function poll() {
    if (running || !endpoint || !drawerPage || document.hidden) return;
    const country = visibleCountry();
    if (!country) return;
    running = true;
    const currentGeneration = generation;
    const priority = country === priorityCountry ? priorityCountry : null;
    priorityCountry = null;
    let warming = false;
    try {
        warming = await readBatch([country], currentGeneration, priority);
    } catch (_) {
        // Cached drawers remain useful offline; the next poll retries quietly.
    } finally {
        running = false;
        if (generation !== currentGeneration || priorityCountry) schedule(0);
        else if (visibleCountry()) schedule(warming ? 5000 : 30000);
    }
}

export function initializeNewsCache() {
    if (started) return;
    started = true;
    endpoint = document.body.dataset.newsCacheUrl;
    document.addEventListener("world-journal:page-ready", event => {
        const page = event.detail.page;
        drawerPage = ["map", "countries"].includes(page) ? page : null;
        schedule(250);
    });
    document.addEventListener("world-journal:page-cleanup", () => {
        generation += 1;
        drawerPage = null;
        priorityCountry = null;
        clearTimeout(timer);
    });
    document.addEventListener("visibilitychange", () => schedule(0));
    document.addEventListener("world-journal:data-changed", event => {
        if (!event.detail?.path?.startsWith("/settings/news/") && !event.detail?.path?.startsWith("/settings/backups/")) return;
        generation += 1;
        invalidatedAt = Date.now();
        entries.clear();
        versions.clear();
        schedule(0);
    });
}
