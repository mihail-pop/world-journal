let registered = false;
let controller = null;

function cleanup() {
    if (!controller) return;
    clearTimeout(controller.timer);
    controller.abort.abort();
    controller = null;
}

async function update(state) {
    if (controller !== state) return;
    let pending = Number(state.page.querySelector("[data-board-pending]")?.dataset.boardPending || 0);
    try {
        if (!document.hidden) {
            const url = new URL(state.page.dataset.resultsUrl, location.origin);
            url.search = state.page.dataset.resultsQuery;
            url.searchParams.set("version", state.page.querySelector("[data-board-version]")?.dataset.boardVersion || "");
            const response = await fetch(url, {signal: state.abort.signal});
            if (!response.ok) throw new Error("News updates are temporarily unavailable. Your saved results remain here.");
            const result = await response.json();
            if (controller !== state || !state.page.isConnected) return;
            if (result.html) {
                const container = state.page.querySelector("[data-news-board-results]");
                const template = document.createElement("template");
                template.innerHTML = result.html;
                // Preserve open summaries/source notices when cached items update.
                const openItems = new Set([...container.querySelectorAll("[data-news-item] details[open]")]
                    .map(details => details.closest("[data-news-item]").dataset.newsItem));
                const noticesOpen = Boolean(container.querySelector(".news-board-status[open]"));
                const focused = container.contains(document.activeElement) ? document.activeElement : null;
                const focusedItem = focused?.closest("[data-news-item]")?.dataset.newsItem;
                const focusSelector = focused?.matches("[data-video-play]") ? "[data-video-play]"
                    : focused?.matches("summary") ? "summary" : focused?.matches("a") ? `a[href="${CSS.escape(focused.getAttribute("href"))}"]` : null;
                container.replaceChildren(template.content);
                for (const card of container.querySelectorAll("[data-news-item]")) {
                    if (openItems.has(card.dataset.newsItem)) card.querySelector("details")?.setAttribute("open", "");
                    if (card.dataset.newsItem === focusedItem && focusSelector) card.querySelector(focusSelector)?.focus({preventScroll: true});
                }
                if (noticesOpen) container.querySelector(".news-board-status")?.setAttribute("open", "");
                window.htmx.process(container);
                pending = result.pending;
            }
            state.page.querySelector("[data-news-board-error]").hidden = true;
        }
    } catch (error) {
        if (error.name === "AbortError") return;
        const message = state.page.querySelector("[data-news-board-error]");
        message.textContent = error.message;
        message.hidden = false;
    }
    if (controller === state) state.timer = setTimeout(() => update(state), pending ? 5000 : 30000);
}

function initialize() {
    cleanup();
    const page = document.querySelector("[data-news-board]");
    if (!page) return;
    page.querySelector("[data-news-apply]").hidden = true;
    controller = {page, abort: new AbortController(), timer: null};
    update(controller);
}

export function registerNewsPage() {
    if (registered) return;
    registered = true;
    document.addEventListener("world-journal:page-ready", initialize);
    document.addEventListener("world-journal:page-cleanup", cleanup);
    document.addEventListener("change", event => {
        const form = event.target.closest?.("[data-news-board-filters]");
        if (form && event.target.matches("select")) window.htmx.trigger(form, "submit");
    });
    document.addEventListener("click", event => {
        const button = event.target.closest("[data-news-board] [data-video-play]");
        if (!button) return;
        document.dispatchEvent(new CustomEvent("world-journal:play-video", {detail: {
            videoId: button.dataset.videoId, title: button.dataset.videoTitle, channel: button.dataset.videoChannel,
        }}));
    });
    document.addEventListener("visibilitychange", () => {
        if (document.hidden || !controller) return;
        clearTimeout(controller.timer);
        // Restart with a new signal so a late hidden-tab response cannot race.
        initialize();
    });
    document.addEventListener("world-journal:data-changed", event => {
        if (!controller || !event.detail?.path?.startsWith("/settings/")) return;
        initialize();
    });
}
