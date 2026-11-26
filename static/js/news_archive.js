// One scroll-driven coverage viewer for Map and Countries. Feed history never
// preloads into all 238 browser drawers and never creates a separate player.
let registered = false;
let generation = 0;
let inlineObserver = null;

function observeInline(root = document) {
    for (const archive of root.querySelectorAll("[data-inline-archive]")) inlineObserver?.observe(archive);
}

function load(details, force = false) {
    const target = details.querySelector("[data-archive-content]");
    if (!target || !details.isConnected || !details.getClientRects().length) return;
    const version = `${generation}:${details.dataset.archiveRevision || ""}:${details.dataset.archiveSource || "all"}`;
    if (!force && (target.dataset.archiveLoaded === version || target.dataset.archivePending === version)) return;
    target.dataset.archiveRequested = version;
    // A newly opened search can arrive before HTMX's settling pass has wired
    // this fragment's custom trigger. Process it before dispatching the event.
    window.htmx?.process(target);
    window.htmx?.trigger(target,"archive-open");
}

export function applyCountryNewsFilter(container, filter = "all") {
    const buttons = [...container.querySelectorAll("[data-news-filter]")];
    if (!buttons.some(button => button.dataset.newsFilter === filter)) filter = "all";
    for (const button of buttons) button.setAttribute("aria-pressed", String(button.dataset.newsFilter === filter));
    for (const item of container.querySelectorAll("[data-news-section]")) item.hidden = filter !== "all" && !item.dataset.newsSection.split(" ").includes(filter);
    const archive = container.querySelector('[data-inline-archive][data-archive-kind="articles"]');
    if (!archive || archive.dataset.archiveSource === filter) return;
    const target = archive.querySelector("[data-archive-content]");
    window.htmx?.trigger(target, "htmx:abort");
    archive.dataset.archiveSource = filter;
    delete target.dataset.archiveLoaded;
    delete target.dataset.archivePending;
    delete target.dataset.archiveRequested;
    target.replaceChildren();
    const url = new URL(target.getAttribute("hx-get"), location.origin);
    url.searchParams.set("source", filter);
    target.setAttribute("hx-get", url.pathname + url.search);
    window.htmx?.process(target);
    inlineObserver?.unobserve(archive);
    inlineObserver?.observe(archive);
}

export function replaceCountryMarkup(container, markup) {
    const template = document.createElement("template");
    template.innerHTML = markup;
    container.replaceChildren(template.content);
    observeInline(container);
    document.dispatchEvent(new CustomEvent("world-journal:news-content-ready"));
}

export function registerNewsArchive() {
    if (registered) return;
    registered = true;
    inlineObserver = new IntersectionObserver(entries => {
        for (const entry of entries) {
            if (!entry.target.isConnected) inlineObserver.unobserve(entry.target);
            else if (entry.isIntersecting) load(entry.target);
        }
    }, {rootMargin: "0px 0px 400px 0px"});
    document.addEventListener("click",event => {
        if (event.target.closest("[data-archive-retry]")) load(event.target.closest("[data-news-archive]"),true);
    });
    document.body.addEventListener("htmx:afterSwap",event => {
        const target = event.detail.target;
        if (target?.matches("[data-archive-content]")) target.dataset.archiveLoaded = target.dataset.archiveRequested;
        observeInline(target || document);
    });
    document.body.addEventListener("htmx:beforeRequest",event => {
        const target = event.detail.elt;
        if (target?.matches("[data-archive-content]")) target.dataset.archivePending = target.dataset.archiveRequested;
    });
    document.body.addEventListener("htmx:afterRequest",event => {
        const target = event.detail.elt;
        if (target?.matches("[data-archive-content]")) delete target.dataset.archivePending;
    });
    document.addEventListener("world-journal:page-ready",() => {
        observeInline();
    });
    document.addEventListener("world-journal:page-cleanup", () => inlineObserver.disconnect());
    document.addEventListener("world-journal:data-changed",event => {
        if (!event.detail?.path?.startsWith("/settings/news/") && !event.detail?.path?.startsWith("/settings/backups/")) return;
        generation++;
        for (const archive of document.querySelectorAll("[data-inline-archive]")) {
            inlineObserver.unobserve(archive);
            inlineObserver.observe(archive);
        }
    });
    observeInline();
}
