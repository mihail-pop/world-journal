// Keep one Map and the last Journal screen in this tab, using their real nodes
// so canvas state, form values, file selections and text cursors survive.
// Other pages still use normal server-rendered HTMX navigation.
const remembered = new Map();
let activePage = null;
let activeUrl = null;
let outgoingUrl = null;
let resumeJournal = false;
let pendingScroll = null;

function currentUrl() {
    return location.pathname + location.search + location.hash;
}

function updateHeaderLinks() {
    for (const link of document.querySelectorAll("[data-nav-page]")) {
        const name = link.dataset.navPage;
        if (name === "map" || name === "journal") {
            link.href = remembered.get(name)?.url ?? (name === "map" ? "/" : "/journal/");
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
    };
}

function restorePosition() {
    const state = pendingScroll;
    pendingScroll = null;
    if (!state) return;
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
    if (activePage && ["map", "journal"].includes(activePage.dataset.page)) {
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
            const preserve = outgoing && ["map", "journal"].includes(outgoing.dataset.page)
                && (outgoing.dataset.page === "map" || name !== "journal" || resumeJournal);
            if (preserve) {
                remembered.set(outgoing.dataset.page, capturePage(outgoing, outgoingUrl ?? activeUrl));
            }
            document.dispatchEvent(new CustomEvent("world-journal:page-cleanup", {
                detail: {preserveMap: true, page: outgoing?.dataset.page},
            }));
            // Detach retained nodes before HTMX's normal cleanup. Discarded pages
            // remain in the target and receive HTMX's ordinary cleanup instead.
            if (preserve) outgoing.remove();
            const saved = remembered.get(name);
            const reuse = saved && (name === "map"
                || (name === "journal" && resumeJournal && saved.url === currentUrl()));
            pendingScroll = reuse ? saved : null;
            if (reuse) incoming.replaceWith(saved.page);
            outgoingUrl = null;
            resumeJournal = false;
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
        resumeJournal = source?.closest("[data-nav-page]")?.dataset.navPage === "journal";
        event.detail.swapOverride = "workspace show:top";
    });
    for (const name of ["htmx:historyCacheHit", "htmx:historyCacheMissLoad"]) {
        document.body.addEventListener(name, event => {
            if (event.detail.historyElt?.id !== "app-content") return;
            outgoingUrl = activeUrl;
            resumeJournal = true;
            event.detail.swapSpec.swapStyle = "workspace";
        });
    }
    document.body.addEventListener("htmx:afterSwap", event => {
        if (event.detail.target?.id !== "app-content" && event.target.id !== "app-content") return;
        activePage = document.querySelector("#app-content > [data-page]");
        activeUrl = currentUrl();
        if (activePage && ["map", "journal"].includes(activePage.dataset.page)) {
            // Replace the one remembered Journal screen after in-Journal
            // navigation/save. A saved/deleted record never resurrects its editor.
            remembered.set(activePage.dataset.page, capturePage(activePage, activeUrl));
        }
        updateHeaderLinks();
    });
    document.body.addEventListener("htmx:afterSettle", restorePosition);
    document.addEventListener("world-journal:location-change", () => {
        if (!activePage?.isConnected) return;
        activeUrl = currentUrl();
        const saved = remembered.get(activePage.dataset.page);
        if (saved?.page === activePage) saved.url = activeUrl;
        updateHeaderLinks();
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
