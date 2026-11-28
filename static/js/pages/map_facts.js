import { refreshJournalVideos } from "./journal_video.js";

function alive(controller, code, id) {
    return !controller.abortController.signal.aborted && controller.selectedCode === code && controller.facts.requestId === id;
}

export function factsSelectionChanged(controller) {
    const state = controller.facts;
    if (!state) return;
    state.requestId += 1;
    state.overviewAbort?.abort();
    state.overviewAbort = null;
    state.content.replaceChildren();
    refreshJournalVideos(state.content);
    delete state.content.dataset.loadedCountry;
    state.content.setAttribute("aria-busy", "false");
}

function showCountryOverview(content, fragment, code) {
    content.replaceChildren(fragment);
    content.dataset.loadedCountry = code;
    window.htmx?.process(content);
    refreshJournalVideos(content);
}

export async function loadCountryOverview(controller, {retry = false} = {}) {
    const state = controller.facts;
    const code = controller.selectedCode;
    if (!code || (!retry && state.overviewAbort)) return;
    if (!retry && state.content.dataset.loadedCountry === code) {
        refreshJournalVideos(state.content);
        return;
    }
    state.overviewAbort?.abort();
    const abort = new AbortController();
    state.overviewAbort = abort;
    const id = ++state.requestId;
    state.content.replaceChildren();
    state.content.setAttribute("aria-busy", "true");
    try {
        const url = controller.page.dataset.countryFactsUrlTemplate.replace("COUNTRY_CODE", encodeURIComponent(code));
        const response = await fetch(url, {signal: abort.signal});
        if (!response.ok) throw new Error("Overview unavailable");
        const template = document.createElement("template");
        template.innerHTML = await response.text();
        if (!alive(controller, code, id)) return;
        if (template.content.querySelector("[data-country-overview-result]")?.dataset.countryOverviewResult !== code) throw new Error("Incorrect overview response");
        showCountryOverview(state.content, template.content, code);
    } catch (error) {
        if (error.name !== "AbortError" && alive(controller, code, id)) {
            state.content.textContent = "Country information could not be loaded. ";
            const button = document.createElement("button");
            button.type = "button";
            button.className = "map-command";
            button.dataset.overviewRetry = "";
            button.textContent = "Retry overview";
            state.content.append(button);
        }
    } finally {
        if (alive(controller, code, id)) {
            state.content.setAttribute("aria-busy", "false");
            state.overviewAbort = null;
        }
    }
}

export function initializeCountryFacts(controller) {
    const signal = controller.abortController.signal;
    const state = controller.facts = {content: controller.page.querySelector("[data-country-overview-content]"), requestId: 0, overviewAbort: null};
    signal.addEventListener("abort", () => factsSelectionChanged(controller), {once: true});
    state.content.addEventListener("click", event => {
        if (event.target.closest("[data-overview-retry]")) loadCountryOverview(controller, {retry: true});
    }, {signal});
    document.addEventListener("world-journal:country-overview-changed", event => {
        if (controller.selectedCode !== event.detail.country) return;
        state.requestId++;
        state.overviewAbort?.abort();
        state.overviewAbort = null;
        const template = document.createElement("template");
        template.innerHTML = event.detail.markup;
        showCountryOverview(state.content, template.content, event.detail.country);
        state.content.setAttribute("aria-busy", "false");
    }, {signal});
}
