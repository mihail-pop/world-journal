// Paging is driven by scrolling or an explicit retry, never by a timer.
const states = new Map();
const configurations = new Map();
let registered = false;

function selector(config, part) {
    return "[data-" + config.prefix + "-" + part + "]";
}

function find(collection, config, part) {
    return collection.querySelector(selector(config, part));
}

function value(collection, config, part) {
    return collection.getAttribute("data-" + config.prefix + "-" + part);
}

function stop(collection) {
    const state = states.get(collection);
    if (!state) return;
    state.active = false;
    state.abort?.abort();
    state.observer?.disconnect();
    const config = state.config;
    const footer = find(collection, config, "pagination");
    if (footer && state.pending) {
        find(footer, config, "more").hidden = false;
        find(footer, config, "loading").hidden = true;
        footer.removeAttribute("aria-busy");
    }
    states.delete(collection);
}

function mount() {
    for (const collection of states.keys()) if (!collection.isConnected) stop(collection);
    for (const config of configurations.values()) for (const collection of document.querySelectorAll("#app-content " + selector(config, "collection"))) {
        if (states.has(collection) || !find(collection, config, "pagination")) continue;
        const state = {collection, config, active: true, pending: false, abort: null, observer: null};
        states.set(collection, state);
        if ("IntersectionObserver" in window) {
            state.observer = new IntersectionObserver(entries => {
                if (entries.some(entry => entry.isIntersecting)) void load(state);
            }, {rootMargin: "0px 0px 500px 0px"});
            const footer = find(collection, config, "pagination");
            if (find(footer, config, "page-error").hidden) state.observer.observe(footer);
        }
    }
}

async function load(state, reload = false) {
    const {collection} = state;
    if (!state.active || state.pending || !collection.isConnected || !collection.getClientRects().length) return;
    const config = state.config;
    const footer = find(collection, config, "pagination");
    if (!footer) return;
    const more = find(footer, config, "more");
    const error = find(footer, config, "page-error");
    const refresh = find(footer, config, "reload");
    const url = reload ? value(collection, config, "refresh-url") : more.href;
    state.pending = true;
    state.observer?.unobserve(footer);
    state.abort = new AbortController();
    const timeout = setTimeout(() => state.abort.abort(), 20000);
    more.hidden = error.hidden = refresh.hidden = true;
    find(footer, config, "loading").hidden = false;
    footer.setAttribute("aria-busy", "true");
    try {
        const response = await fetch(url, {signal: state.abort.signal, headers: {[config.header]: "1"}});
        if (!state.active) return;
        if (response.status === 409) {
            error.textContent = config.changedMessage;
            error.hidden = refresh.hidden = false;
            return;
        }
        if (!response.ok) throw new Error("The next results could not be loaded. Try again.");
        const template = document.createElement("template");
        template.innerHTML = await response.text();
        if (!state.active || !collection.isConnected) return;
        const incoming = template.content.querySelector(selector(config, "collection"));
        if (!incoming || !reload && (value(incoming, config, "query") !== value(collection, config, "query")
            || value(incoming, config, "version") !== value(collection, config, "version"))) {
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
        const list = find(collection, config, "items");
        const items = find(incoming, config, "items");
        if (!list || !items) throw new Error("The next results could not be loaded. Try again.");
        const seen = new Set([...list.children].map(item => value(item, config, "item")));
        for (const item of [...items.children]) {
            if (seen.has(value(item, config, "item"))) continue;
            seen.add(value(item, config, "item"));
            list.append(item);
            window.htmx?.process(item);
        }
        const next = find(incoming, config, "pagination");
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
            find(footer, config, "loading").hidden = true;
            footer.removeAttribute("aria-busy");
        }
    }
}

export function registerInfiniteScroll(config) {
    if (configurations.has(config.prefix)) return;
    configurations.set(config.prefix, config);
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
        const selectors = [...configurations.values()].flatMap(config => [selector(config, "more"), selector(config, "reload")]);
        const button = event.target.closest(selectors.join(", "));
        if (!button || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const config = [...configurations.values()].find(config => button.matches(selector(config, "more") + ", " + selector(config, "reload")));
        const collection = button.closest(selector(config, "collection"));
        const reload = button.matches(selector(config, "reload"));
        event.preventDefault();
        event.stopImmediatePropagation();
        if (reload && collection.matches(config.reloadCollection)) {
            const form = collection.closest(config.reloadRoot)?.querySelector(config.reloadForm);
            if (form) window.htmx?.trigger(form, "submit");
            return;
        }
        mount();
        const state = states.get(collection);
        if (state) void load(state, reload);
    }, true);
}
