// Retain rendered drawers independently of page swaps. This cache contains HTML,
// not live DOM nodes: video thumbnails and players are mounted only on demand.
const entries = new Map();
const versions = new Map();
let generation = 0;
let selectedCountry = null;
let timer = null;
let running = false;
let started = false;
let endpoint;
let countries = [];
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
    selectedCountry = code;
    if (!running) schedule(0);
}

function schedule(delay) {
    clearTimeout(timer);
    timer = setTimeout(poll, delay);
}

async function readBatch(codes, currentGeneration) {
    const url = new URL(endpoint, location.origin);
    if (codes.length) {
        url.searchParams.set("countries", codes.join(","));
        url.searchParams.set("versions", codes.map(code => versions.get(code) || "").join(","));
    }
    if (selectedCountry && countries.includes(selectedCountry)) url.searchParams.set("priority", selectedCountry);
    const requestedAt = Date.now();
    const response = await fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
    if (!response.ok) throw new Error("Feed cache is temporarily unavailable");
    const result = await response.json();
    if (generation !== currentGeneration) return null;
    countries = result.countries;
    if (selectedCountry && !countries.includes(selectedCountry)) selectedCountry = null;
    for (const [code, record] of Object.entries(result.records)) {
        rememberCountryFeed(code, "articles", record.articles, { requestedAt, version: record.version });
        rememberCountryFeed(code, "videos", record.videos, { requestedAt, version: record.version });
        versions.set(code, record.version);
    }
    return result.warming;
}

async function poll() {
    if (running || !endpoint) return;
    if (document.hidden) { schedule(30000); return; }
    running = true;
    const currentGeneration = generation;
    let warming = false;
    try {
        if (!countries.length) warming = await readBatch([], currentGeneration);
        const ordered = selectedCountry
            ? [selectedCountry, ...countries.filter(code => code !== selectedCountry)]
            : [...countries];
        for (let index = 0; index < ordered.length && generation === currentGeneration && !document.hidden; index += 20) {
            warming = await readBatch(ordered.slice(index, index + 20), currentGeneration) || warming;
            // Spread HTML preparation out instead of competing with the map's first render.
            await new Promise(resolve => setTimeout(resolve, 100));
        }
    } catch (_) {
        // Cached drawers remain useful offline; the next poll retries quietly.
    } finally {
        running = false;
        schedule(generation !== currentGeneration ? 0 : warming ? 5000 : 30000);
    }
}

export function initializeNewsCache() {
    if (started) return;
    started = true;
    endpoint = document.body.dataset.newsCacheUrl;
    const requested = new URL(location.href).searchParams.get("country");
    if (/^[A-Z]{2}$/i.test(requested || "")) selectedCountry = requested.toUpperCase();
    document.addEventListener("visibilitychange", () => { if (!document.hidden && !running) schedule(0); });
    document.addEventListener("world-journal:data-changed", event => {
        if (!event.detail?.path?.startsWith("/settings/news/") && !event.detail?.path?.startsWith("/settings/backups/")) return;
        generation += 1;
        invalidatedAt = Date.now();
        entries.clear();
        versions.clear();
        if (!running) schedule(0);
    });
    schedule(250);
}
