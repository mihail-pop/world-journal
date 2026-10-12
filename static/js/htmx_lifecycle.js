import { registerPageMemory } from "./page_memory.js";

const PAGE_LABELS = {
    map: "Map",
    news: "News",
    countries: "Countries",
    journal: "Journal",
    settings: "Settings",
};

function initializePage(root = document) {
    const page = root.querySelector("[data-page]");
    if (!page) {
        return;
    }

    const pageName = page.dataset.page;
    document.querySelectorAll("[data-nav-page]").forEach((link) => {
        if (link.dataset.navPage === pageName) {
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
    registerPageMemory();
    initializePage();

    document.body.addEventListener("htmx:afterSwap", (event) => {
        const target = event.detail.target ?? event.target;
        if (target?.id === "app-content") {
            initializePage(target);
        }
    });

    document.body.addEventListener("htmx:historyRestore", () => initializePage());
}
