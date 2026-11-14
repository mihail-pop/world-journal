let registered = false;

export function registerNewsPage() {
    if (registered) return;
    registered = true;
    document.addEventListener("world-journal:page-ready", () => {
        const button = document.querySelector("[data-news-apply]");
        if (button) button.hidden = true;
    });
    document.addEventListener("change", event => {
        const form = event.target.closest?.("[data-news-board-filters]");
        if (form && event.target.matches("select")) window.htmx.trigger(form, "submit");
    });
    document.addEventListener("click", event => {
        const button = event.target.closest("[data-news-board] [data-video-play]");
        if (!button) return;
        const bookmark = button.closest("[data-news-item]").querySelector(".news-save-journal");
        document.dispatchEvent(new CustomEvent("world-journal:play-video", {detail: {
            videoId: button.dataset.videoId, title: button.dataset.videoTitle, channel: button.dataset.videoChannel,
            saveUrl: bookmark?.dataset.bookmarkUrl || bookmark?.href,
        }}));
    });
}
