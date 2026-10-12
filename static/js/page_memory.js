// Keep one Map and the last Journal/News/Countries screens using their real nodes
// so canvas state, form values, file selections and text cursors survive.
// Other pages still use normal server-rendered HTMX navigation.
const remembered = new Map();
let activePage = null;
let activeUrl = null;
let outgoingUrl = null;
let resumeJournal = false;
let resumeNews = false;
let resumeCountries = false;
let pendingScroll = null;
let resetPage = null;
let pendingTop = false;

function currentUrl() {
    return location.pathname + location.search + location.hash;
}

function updateHeaderLinks() {
    for (const link of document.querySelectorAll("[data-nav-page]")) {
        const name = link.dataset.navPage;
        if (["map", "journal", "news", "countries"].includes(name)) {
            const root = name === "map" ? "/" : `/${name}/`;
            link.href = activePage?.dataset.page === name ? root : remembered.get(name)?.url ?? root;
        }
    }
}

function capturePage(page, url) {
    return {
        page, url,
        windowScroll: [window.scrollX, window.scrollY],
        scrolls: [page, ...page.querySelectorAll("*")]
            .filter(element => element.scrollTop || element.scrollLeft)
            .map(element => [element, element.scrollLeft, element.scrollTop]),
        focus: page.contains(document.activeElement) ? document.activeElement : null,
        journalDirty: remembered.get(page.dataset.page)?.journalDirty || false,
    };
}

function restorePosition() {
    const state = pendingScroll;
    pendingScroll = null;
    if (!state) {
        if (pendingTop) requestAnimationFrame(() => window.scrollTo({top: 0, left: 0, behavior: "instant"}));
        pendingTop = false;
        return;
    }
    pendingTop = false;
    // HTMX applies its own show/scroll after afterSettle; restore afterward.
    requestAnimationFrame(() => {
        if (activePage !== state.page || !state.page.isConnected) return;
        if (state.focus?.isConnected && !state.focus.disabled) state.focus.focus({preventScroll: true});
        for (const [element, left, top] of state.scrolls) {
            element.scrollLeft = left;
            element.scrollTop = top;
        }
        window.scrollTo({left: state.windowScroll[0], top: state.windowScroll[1], behavior: "instant"});
    });
}

export function registerPageMemory() {
    activePage = document.querySelector("#app-content > [data-page]");
    activeUrl = currentUrl();
    if (activePage && ["map", "journal", "news", "countries"].includes(activePage.dataset.page)) {
        remembered.set(activePage.dataset.page, capturePage(activePage, activeUrl));
    }
    updateHeaderLinks();

    window.htmx.defineExtension("page-memory", {
        handleSwap(style, target, fragment) {
            if (style !== "workspace" || target.id !== "app-content") return false;
            const incoming = fragment.querySelector("[data-page]");
            if (!incoming) return false;
            const outgoing = target.querySelector(":scope > [data-page]");
            const name = incoming.dataset.page;
            const preserve = outgoing && ["map", "journal", "news", "countries"].includes(outgoing.dataset.page)
                && resetPage !== outgoing.dataset.page
                && (outgoing.dataset.page === "map"
                    || outgoing.dataset.page === "journal" && (name !== "journal" || resumeJournal)
                    || outgoing.dataset.page === "news" && (name !== "news" || resumeNews)
                    || outgoing.dataset.page === "countries" && (name !== "countries" || resumeCountries));
            if (preserve) {
                remembered.set(outgoing.dataset.page, capturePage(outgoing, outgoingUrl ?? activeUrl));
            }
            document.dispatchEvent(new CustomEvent("world-journal:page-cleanup", {
                detail: {preserveMap: resetPage !== "map", preserveJournal: Boolean(preserve && outgoing.dataset.page === "journal"), preserveCountries: Boolean(preserve && outgoing.dataset.page === "countries"), page: outgoing?.dataset.page},
            }));
            // Detach retained nodes before HTMX's normal cleanup. Discarded pages
            // remain in the target and receive HTMX's ordinary cleanup instead.
            if (preserve) outgoing.remove();
            if (resetPage) remembered.delete(resetPage);
            const saved = remembered.get(name);
            const refreshJournal = name === "journal" && resumeJournal && saved?.url === currentUrl()
                && saved.journalDirty && !saved.page.querySelector("[data-journal-editor]");
            const reuse = !refreshJournal && saved && (name === "map"
                || (name === "journal" && resumeJournal && saved.url === currentUrl())
                || (name === "news" && resumeNews && saved.url === currentUrl())
                || (name === "countries" && resumeCountries && saved.url === currentUrl()));
            pendingScroll = refreshJournal ? {...saved, page: incoming, scrolls: [], focus: null} : reuse ? saved : null;
            if (name === "journal" && !reuse && saved) saved.journalDirty = false;
            pendingTop = !reuse;
            if (reuse && name === "news") {
                // Keep the reading position but use current source choices from
                // the server, including switches changed while News was away.
                for (const selector of ["[data-news-board-filters]", ".news-board-tabs"]) {
                    const current = incoming.querySelector(selector);
                    if (current) saved.page.querySelector(selector)?.replaceWith(current);
                }
                saved.page.dataset.resultsQuery = incoming.dataset.resultsQuery;
                const currentArchive = incoming.querySelector("[data-news-archive]");
                const oldArchive = saved.page.querySelector("[data-news-archive]");
                if (currentArchive && oldArchive) {
                    if (["archiveCountry","archiveKind","archiveSource","archiveConfig"].some(key => oldArchive.dataset[key] !== currentArchive.dataset[key])) oldArchive.replaceWith(currentArchive);
                    else oldArchive.dataset.archiveRevision = currentArchive.dataset.archiveRevision;
                }
            }
            if (reuse) incoming.replaceWith(saved.page);
            outgoingUrl = null;
            resumeJournal = false;
            resumeNews = false;
            resumeCountries = false;
            resetPage = null;
            // Fall back to HTMX's innerHTML swap with the prepared fragment. It
            // still owns node processing, history, focus and all swap events.
            return false;
        },
    });

    document.body.addEventListener("htmx:configRequest", event => {
        const link = event.detail.elt?.closest("[data-nav-page]");
        // Boosted anchors capture href when first processed. Read the current
        // remembered href here too, so the sent request and history agree.
        if (link && event.detail.verb === "get") event.detail.path = link.getAttribute("href");
    });
    document.body.addEventListener("htmx:beforeSwap", event => {
        if (event.detail.target?.id !== "app-content" || !event.detail.shouldSwap) return;
        outgoingUrl = currentUrl();
        const source = event.detail.requestConfig?.elt;
        const navPage = source?.closest("[data-nav-page]")?.dataset.navPage;
        resetPage = navPage === activePage?.dataset.page ? navPage : null;
        resumeJournal = navPage === "journal" && !resetPage;
        resumeNews = navPage === "news" && !resetPage;
        resumeCountries = navPage === "countries" && !resetPage;
        event.detail.swapOverride = "workspace show:top";
    });
    for (const name of ["htmx:historyCacheHit", "htmx:historyCacheMissLoad"]) {
        document.body.addEventListener(name, event => {
            if (event.detail.historyElt?.id !== "app-content") return;
            outgoingUrl = activeUrl;
            resetPage = null;
            resumeJournal = true;
            resumeNews = true;
            resumeCountries = true;
            event.detail.swapSpec.swapStyle = "workspace";
        });
    }
    document.body.addEventListener("htmx:afterSwap", event => {
        if (event.detail.target?.id !== "app-content" && event.target.id !== "app-content") return;
        activePage = document.querySelector("#app-content > [data-page]");
        activeUrl = currentUrl();
        if (activePage && ["map", "journal", "news", "countries"].includes(activePage.dataset.page)) {
            // Replace the one remembered Journal screen after in-Journal
            // navigation/save. A saved/deleted record never resurrects its editor.
            remembered.set(activePage.dataset.page, capturePage(activePage, activeUrl));
        }
        updateHeaderLinks();
    });
    document.body.addEventListener("htmx:afterSettle", event => {
        if (event.detail.target?.id === "app-content" || event.target.id === "app-content") restorePosition();
    });
    document.addEventListener("world-journal:location-change", () => {
        if (!activePage?.isConnected) return;
        activeUrl = currentUrl();
        const saved = remembered.get(activePage.dataset.page);
        if (saved?.page === activePage) saved.url = activeUrl;
        updateHeaderLinks();
    });
    document.addEventListener("world-journal:map-preset-saved", event => {
        // A map save can finish while Journal/Settings is visible. Keep the
        // remembered URL pointed at the newly saved preset when returning.
        const saved = remembered.get("map");
        if (!saved) return;
        const url = new URL(saved.url, location.origin);
        if (url.searchParams.get("edit_preset") !== event.detail.previousId) return;
        url.searchParams.set("edit_preset", event.detail.id);
        saved.url = url.pathname + url.search + url.hash;
        updateHeaderLinks();
    });
    document.addEventListener("world-journal:journal-autosaved", event => {
        const saved = remembered.get("journal");
        if (saved?.page.contains(event.detail.form)) {
            saved.url = event.detail.url;
            updateHeaderLinks();
        }
    });
    document.addEventListener("world-journal:data-changed", event => {
        if (event.detail?.path !== document.body.dataset.journalQuickSaveUrl) return;
        const saved = remembered.get("journal");
        if (saved) saved.journalDirty = true;
    });
    document.body.addEventListener("htmx:afterRequest", event => {
        const config = event.detail.requestConfig;
        if (event.detail.successful && config && config.verb.toLowerCase() !== "get") {
            document.dispatchEvent(new CustomEvent("world-journal:data-changed", {
                detail: {path: new URL(config.path, location.href).pathname},
            }));
        }
    });
}
