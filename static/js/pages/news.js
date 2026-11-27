import { dismissNotice, notify } from "../notifications.js";

let registered = false;
let searchTimer = null;

function updateTabLinks(form) {
    const values = new URLSearchParams(new FormData(form));
    values.delete("source");
    for (const link of form.closest("[data-news-board]").querySelectorAll(".news-board-tabs a")) {
        const url = new URL(link.href);
        const videos = url.searchParams.get("tab") === "videos";
        const next = new URLSearchParams(values);
        next.set("tab", videos ? "videos" : "articles");
        next.set("sort", videos ? "views" : "top");
        link.href = `${url.pathname}?${next}`;
    }
}

function submit(form) {
    clearTimeout(searchTimer);
    searchTimer = null;
    if (form.isConnected) form.requestSubmit();
}

export function registerNewsPage() {
    if (registered) return;
    registered = true;
    document.addEventListener("world-journal:page-cleanup", () => {
        clearTimeout(searchTimer);
        searchTimer = null;
    });
    document.addEventListener("input", event => {
        if (!event.target.matches("[data-news-search]") || event.isComposing) return;
        clearTimeout(searchTimer);
        const form = event.target.form;
        updateTabLinks(form);
        searchTimer = setTimeout(() => submit(form), 300);
    });
    document.addEventListener("compositionend", event => {
        if (event.target.matches("[data-news-search]")) event.target.dispatchEvent(new Event("input", {bubbles: true}));
    });
    document.addEventListener("keydown", event => {
        if (event.key !== "Enter" || event.isComposing || !event.target.matches("[data-news-search]")) return;
        event.preventDefault();
        submit(event.target.form);
    });
    document.addEventListener("submit", event => {
        if (!event.target.matches("[data-news-board-filters]")) return;
        clearTimeout(searchTimer);
        searchTimer = null;
        updateTabLinks(event.target);
    }, true);
    document.addEventListener("change", event => {
        const form = event.target.closest?.("[data-news-board-filters]");
        if (form && event.target.matches("select")) submit(form);
    });
    document.addEventListener("click", event => {
        const sort = event.target.closest("[data-news-sort]");
        if (sort) {
            const form = sort.form;
            const input = form.elements.namedItem("sort");
            input.value = sort.dataset.next;
            const videos = form.elements.namedItem("tab").value === "videos";
            const descending = input.value === (videos ? "views" : "top");
            const label = videos ? (descending ? "Most viewed" : "Least viewed") : (descending ? "Top stories" : "Newest");
            sort.dataset.order = descending ? "desc" : "asc";
            sort.dataset.next = descending ? (videos ? "least_views" : "newest") : (videos ? "views" : "top");
            sort.title = label;
            sort.setAttribute("aria-label", `Sort: ${label}`);
            submit(form);
            return;
        }
        const summary = event.target.closest("[data-news-summary-toggle]");
        if (summary) {
            summary.setAttribute("aria-expanded", String(summary.getAttribute("aria-expanded") !== "true"));
            return;
        }
        const button = event.target.closest("[data-news-board] [data-video-play]");
        if (!button) return;
        const bookmark = button.closest("[data-news-item]").querySelector(".news-save-journal");
        document.dispatchEvent(new CustomEvent("world-journal:play-video", {detail: {
            videoId: button.dataset.videoId, title: button.dataset.videoTitle, channel: button.dataset.videoChannel,
            saveUrl: bookmark?.dataset.bookmarkUrl || bookmark?.href,
        }}));
    });
    document.body.addEventListener("htmx:afterSettle", event => {
        if (event.detail.target?.matches("[data-news-board-results]")) document.dispatchEvent(new CustomEvent("world-journal:location-change"));
    });
    document.body.addEventListener("htmx:beforeRequest", event => {
        if (event.detail.elt?.matches("[data-news-board-filters]")) dismissNotice("news-filters-error");
    });
    for (const name of ["htmx:responseError", "htmx:sendError", "htmx:timeout"]) {
        document.body.addEventListener(name, event => {
            if (event.detail.elt?.matches("[data-news-board-filters]")) {
                notify({id: "news-filters-error", kind: "error", title: "News could not be loaded", message: "Your current results are still shown. Check the connection and try again."});
            }
        });
    }
}
