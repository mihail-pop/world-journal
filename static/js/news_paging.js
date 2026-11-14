import { registerInfiniteScroll } from "./infinite_scroll.js";

export function registerNewsPaging() {
    registerInfiniteScroll({
        prefix: "news",
        header: "X-News-Paging",
        changedMessage: "News has changed. Refresh these results to continue.",
        reloadCollection: ".news-board-result",
        reloadRoot: "[data-news-board]",
        reloadForm: "[data-news-board-filters]",
    });
}
