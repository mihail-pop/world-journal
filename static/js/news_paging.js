// Paging is driven by scrolling or an explicit retry, never by a timer.
const states = new Map();
let registered = false;

function stop(collection) {
    const state = states.get(collection);
    if (!state) return;
    state.active = false;
    state.abort?.abort();
    state.observer?.disconnect();
    const footer = collection.querySelector("[data-news-pagination]");
    if (footer && state.pending) {
        footer.querySelector("[data-news-more]").hidden = false;
        footer.querySelector("[data-news-loading]").hidden = true;
        footer.removeAttribute("aria-busy");
    }
    states.delete(collection);
}

function mount() {
    for (const collection of states.keys()) if (!collection.isConnected) stop(collection);
    for (const collection of document.querySelectorAll("#app-content [data-news-collection]")) {
        if (states.has(collection) || !collection.querySelector("[data-news-pagination]")) continue;
        const state = {collection, active: true, pending: false, abort: null, observer: null};
        states.set(collection, state);
        if ("IntersectionObserver" in window) {
            state.observer = new IntersectionObserver(entries => {
                if (entries.some(entry => entry.isIntersecting)) void load(state);
            }, {rootMargin: "0px 0px 500px 0px"});
            const footer = collection.querySelector("[data-news-pagination]");
            if (footer.querySelector("[data-news-page-error]").hidden) state.observer.observe(footer);
        }
    }
}

async function load(state, reload = false) {
    const {collection} = state;
    if (!state.active || state.pending || !collection.isConnected || !collection.getClientRects().length) return;
    const footer = collection.querySelector("[data-news-pagination]");
    if (!footer) return;
    const more = footer.querySelector("[data-news-more]");
    const error = footer.querySelector("[data-news-page-error]");
    const refresh = footer.querySelector("[data-news-reload]");
    const url = reload ? collection.dataset.newsRefreshUrl : more.href;
    state.pending = true;
    state.observer?.unobserve(footer);
    state.abort = new AbortController();
    const timeout = setTimeout(() => state.abort.abort(), 20000);
    more.hidden = error.hidden = refresh.hidden = true;
    footer.querySelector("[data-news-loading]").hidden = false;
    footer.setAttribute("aria-busy", "true");
    try {
        const response = await fetch(url, {signal: state.abort.signal, headers: {"X-News-Paging": "1"}});
        if (!state.active) return;
        if (response.status === 409) {
            error.textContent = "News has changed. Refresh these results to continue.";
            error.hidden = refresh.hidden = false;
            return;
        }
        if (!response.ok) throw new Error("The next results could not be loaded. Try again.");
        const template = document.createElement("template");
        template.innerHTML = await response.text();
        if (!state.active || !collection.isConnected) return;
        const incoming = template.content.querySelector("[data-news-collection]");
        if (!incoming || !reload && (incoming.dataset.newsQuery !== collection.dataset.newsQuery
            || incoming.dataset.newsVersion !== collection.dataset.newsVersion)) {
            throw new Error("These results changed. Refresh this view and try again.");
        }
        if (reload) {
            stop(collection);
            collection.replaceWith(incoming);
            incoming.scrollIntoView({block: "start", behavior: "instant"});
            window.htmx?.process(incoming);
            mount();
            return;
        }
        const list = collection.querySelector("[data-news-items]");
        const items = incoming.querySelector("[data-news-items]");
        if (!list || !items) throw new Error("The next results could not be loaded. Try again.");
        const seen = new Set([...list.children].map(item => item.dataset.newsItem));
        for (const item of [...items.children]) {
            if (seen.has(item.dataset.newsItem)) continue;
            seen.add(item.dataset.newsItem);
            list.append(item);
            window.htmx?.process(item);
        }
        const next = incoming.querySelector("[data-news-pagination]");
        if (next) {
            footer.replaceWith(next);
            state.observer?.observe(next);
        } else {
            footer.remove();
            stop(collection);
        }
    } catch (failure) {
        if (!state.active) return;
        error.textContent = failure.name === "AbortError" ? "Loading timed out. Try again." : failure.message;
        error.hidden = false;
        more.textContent = "Retry";
        more.hidden = false;
    } finally {
        clearTimeout(timeout);
        state.pending = false;
        if (state.active && footer.isConnected) {
            footer.querySelector("[data-news-loading]").hidden = true;
            footer.removeAttribute("aria-busy");
        }
    }
}

export function registerNewsPaging() {
    if (registered) return;
    registered = true;
    document.addEventListener("world-journal:page-ready", mount);
    document.addEventListener("world-journal:page-cleanup", () => {
        for (const collection of [...states.keys()]) stop(collection);
    });
    document.body.addEventListener("htmx:beforeSwap", event => {
        const target = event.detail.target;
        if (!target) return;
        for (const collection of [...states.keys()]) if (target.contains(collection)) stop(collection);
    });
    document.body.addEventListener("htmx:afterSwap", mount);
    document.addEventListener("click", event => {
        const button = event.target.closest("[data-news-more], [data-news-reload]");
        if (!button || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const collection = button.closest("[data-news-collection]");
        const reload = button.matches("[data-news-reload]");
        event.preventDefault();
        event.stopImmediatePropagation();
        if (reload && collection.matches(".news-board-result")) {
            window.htmx?.trigger(collection.closest("[data-news-board]").querySelector("[data-news-board-filters]"), "submit");
            return;
        }
        mount();
        const state = states.get(collection);
        if (state) void load(state, reload);
    }, true);
}
