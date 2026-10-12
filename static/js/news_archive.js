// One lazy archive viewer for Map, Countries and News. Feed history never
// preloads into all 238 browser drawers and never creates a separate player.
let registered = false;
let generation = 0;

function load(details, force = false) {
    const target = details.querySelector("[data-archive-content]");
    if (!target || !details.isConnected) return;
    const version = `${generation}:${details.dataset.archiveRevision || ""}`;
    if (!force && target.dataset.archiveLoaded === version) return;
    target.dataset.archiveRequested = version;
    window.htmx?.trigger(target,"archive-open");
}

export function replaceCountryMarkup(container, markup) {
    const template = document.createElement("template");
    template.innerHTML = markup;
    const previous = container.querySelector("[data-news-archive]");
    const next = template.content.querySelector("[data-news-archive]");
    if (previous?.open && next && ["archiveCountry","archiveKind","archiveConfig"].every(key => previous.dataset[key] === next.dataset[key])) {
        // Keep the actual reader and its page while the live feed updates.
        previous.dataset.archiveRevision = next.dataset.archiveRevision;
        next.replaceWith(previous);
    }
    container.replaceChildren(template.content);
}

export function registerNewsArchive() {
    if (registered) return;
    registered = true;
    document.addEventListener("toggle",event => {
        if (event.target.matches?.("[data-news-archive]") && event.target.open) load(event.target);
    },true);
    document.addEventListener("click",event => {
        if (event.target.closest("[data-archive-retry]")) load(event.target.closest("[data-news-archive]"),true);
    });
    document.body.addEventListener("htmx:afterSwap",event => {
        const target = event.detail.target;
        if (target?.matches("[data-archive-content]")) target.dataset.archiveLoaded = target.dataset.archiveRequested;
    });
    document.addEventListener("world-journal:page-ready",() => {
        for (const details of document.querySelectorAll("[data-news-archive][open]")) load(details);
    });
    document.addEventListener("world-journal:data-changed",event => {
        if (!event.detail?.path?.startsWith("/settings/news/") && !event.detail?.path?.startsWith("/settings/backups/")) return;
        generation++;
        for (const details of document.querySelectorAll("[data-news-archive][open]")) load(details,true);
    });
}
