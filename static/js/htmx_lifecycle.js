const PAGE_LABELS = {
    map: "Map",
    journal: "Journal",
    settings: "Settings",
};

function initializePage(root = document) {
    const page = root.querySelector("[data-page]");
    if (!page) {
        return;
    }

    const pageName = page.dataset.page;
    document.querySelectorAll(".primary-nav a").forEach((link) => {
        if (new URL(link.href).pathname === window.location.pathname) {
            link.setAttribute("aria-current", "page");
        } else {
            link.removeAttribute("aria-current");
        }
    });
    const appName = document.documentElement.dataset.appName;
    document.title = `${PAGE_LABELS[pageName] ?? appName} | ${appName}`;
    document.dispatchEvent(new CustomEvent("world-journal:page-ready", { detail: { page: pageName } }));
}

export function registerHtmxLifecycle() {
    initializePage();

    document.body.addEventListener("htmx:beforeSwap", (event) => {
        const target = event.detail.target ?? event.target;
        if (target?.id === "app-content") {
            document.dispatchEvent(new CustomEvent("world-journal:page-cleanup"));
        }
    });

    document.body.addEventListener("htmx:afterSwap", (event) => {
        const target = event.detail.target ?? event.target;
        if (target?.id === "app-content") {
            initializePage(target);
        }
    });

    document.body.addEventListener("htmx:historyRestore", () => initializePage());
}