const PRESET_LAYER = "world-journal-country-presets";
const FAVORITE_LAYER = "world-journal-country-favorites";
const COLOR = /^#[0-9a-f]{6}$/i;
let editorRegistered = false;

function isAlive(controller) {
    return !controller.abortController.signal.aborted;
}

function validColors(snapshot) {
    return Object.fromEntries(Object.entries(snapshot.colors || {}).filter(([code, color]) => /^[A-Z]{2}$/.test(code) && COLOR.test(color)));
}

export function applyPersonalLayers(controller) {
    const {map, personal} = controller;
    if (!map || !personal || !controller.layersInstalled) return;
    const colors = Object.entries(personal.colors).flat();
    const fallback = COLOR.test(personal.defaultColor) ? personal.defaultColor : "rgba(0,0,0,0)";
    if (map.getLayer(PRESET_LAYER)) {
        map.setPaintProperty(PRESET_LAYER, "fill-color", colors.length ? ["match", ["get", "iso_a2"], ...colors, fallback] : fallback);
    }
    if (map.getLayer("world-journal-country-small-marker")) {
        const accent = getComputedStyle(document.documentElement).getPropertyValue("--special-color").trim();
        const markerFallback = COLOR.test(personal.defaultColor) ? personal.defaultColor : accent;
        map.setPaintProperty("world-journal-country-small-marker", "circle-color", colors.length ? ["match", ["get", "iso_a2"], ...colors, markerFallback] : markerFallback);
    }
    if (map.getLayer(FAVORITE_LAYER)) {
        map.setFilter(FAVORITE_LAYER, ["in", ["get", "iso_a2"], ["literal", [...personal.favorites]]]);
    }
}

function updatePersonalControls(controller) {
    const state = controller.personal;
    if (!isAlive(controller)) return;
    const jump = controller.page.querySelector("[data-favorite-jump]");
    jump.replaceChildren(new Option(state.favorites.size ? "Jump to a favorite…" : "No favorites yet", ""));
    for (const country of [...controller.countriesByCode.values()].filter(country => state.favorites.has(country.iso_a2)).sort((a, b) => a.name.localeCompare(b.name))) {
        jump.add(new Option(country.name, country.iso_a2));
    }
    jump.disabled = !state.ready || !state.favorites.size;
    const select = controller.page.querySelector("[data-active-preset]");
    select.replaceChildren(new Option("No preset", ""));
    for (const preset of state.presets) select.add(new Option(preset.name, preset.id));
    select.value = state.activePreset || "";
    select.disabled = !state.ready || state.activating;
    const button = controller.page.querySelector("[data-country-favorite]");
    const favored = state.favorites.has(controller.selectedCode);
    button.setAttribute("aria-label", favored ? "Remove country from favorites" : "Add country to favorites");
    button.title = favored ? "Remove from favorites" : "Add to favorites";
    button.setAttribute("aria-pressed", String(favored));
    button.disabled = !state.ready || !controller.selectedCode || state.favoritePending.has(controller.selectedCode);
    applyPersonalLayers(controller);
}

async function post(controller, url, params) {
    const response = await fetch(url, {
        method: "POST", body: new URLSearchParams(params), signal: controller.abortController.signal,
        headers: {"Accept": "application/json", "X-CSRFToken": controller.page.querySelector('[name="csrfmiddlewaretoken"]').value},
    });
    if (!response.ok) throw new Error("Saved map data unavailable");
    return response.json();
}

export async function loadPersonalData(controller) {
    const state = controller.personal;
    const id = ++state.loadId;
    state.status.textContent = "Loading saved map data…";
    state.retry.hidden = true;
    try {
        const response = await fetch(controller.page.dataset.mapPersonalUrl, {signal: controller.abortController.signal, cache: "no-store"});
        if (!response.ok) throw new Error("Saved map data unavailable");
        const snapshot = await response.json();
        if (!isAlive(controller) || id !== state.loadId) return;
        state.favorites = new Set(snapshot.favorites);
        state.presets = snapshot.presets;
        state.activePreset = snapshot.active_preset;
        state.defaultColor = snapshot.default_color;
        state.colors = validColors(snapshot);
        state.ready = true;
        state.status.textContent = state.activePreset ? "Preset colors are active." : "";
        updatePersonalControls(controller);
    } catch (error) {
        if (error.name !== "AbortError" && isAlive(controller) && id === state.loadId) {
            state.status.textContent = "Saved map data could not be loaded. The ordinary map is still available.";
            state.retry.hidden = false;
        }
    }
}

export function personalSelectionChanged(controller) {
    const state = controller.personal;
    if (!state) return;
    state.notesId += 1;
    state.notesAbort?.abort();
    state.notesAbort = null;
    state.notesContent.replaceChildren();
    state.notesContent.setAttribute("aria-busy", "false");
    delete state.notesContent.dataset.loadedCountry;
    state.favoriteStatus.textContent = "";
    updatePersonalControls(controller);
}

export async function loadCountryNotes(controller, {retry = false} = {}) {
    const state = controller.personal;
    const code = controller.selectedCode;
    if (!code || (!retry && (state.notesAbort || state.notesContent.dataset.loadedCountry === code))) return;
    state.notesAbort?.abort();
    const abort = new AbortController();
    state.notesAbort = abort;
    const id = ++state.notesId;
    const content = state.notesContent;
    content.textContent = "Loading your saved country notes…";
    content.setAttribute("aria-busy", "true");
    try {
        const response = await fetch(controller.page.dataset.countryNotesUrlTemplate.replace("COUNTRY_CODE", encodeURIComponent(code)), {signal: abort.signal, cache: "no-store"});
        if (!response.ok) throw new Error("Notes unavailable");
        const html = await response.text();
        if (!isAlive(controller) || id !== state.notesId || controller.selectedCode !== code) return;
        const template = document.createElement("template");
        template.innerHTML = html;
        if (template.content.querySelector("[data-country-notes-result]")?.dataset.countryNotesResult !== code) throw new Error("Incorrect notes response");
        content.replaceChildren(template.content);
        content.dataset.loadedCountry = code;
        window.htmx?.process(content);
    } catch (error) {
        if (error.name !== "AbortError" && isAlive(controller) && id === state.notesId && controller.selectedCode === code) {
            content.textContent = "Your saved notes could not be loaded. They remain in the Journal. ";
            const button = document.createElement("button");
            button.type = "button";
            button.className = "map-command";
            button.dataset.countryNotesRetry = "";
            button.textContent = "Retry";
            content.append(button);
        }
    } finally {
        if (id === state.notesId) {
            content.setAttribute("aria-busy", "false");
            state.notesAbort = null;
        }
    }
}

export function initializePersonalMap(controller, selectCountry) {
    const {page} = controller;
    const signal = controller.abortController.signal;
    const state = controller.personal = {
        ready: false, favorites: new Set(), presets: [], colors: {}, defaultColor: "", activePreset: null,
        favoritePending: new Set(), activating: false, loadId: 0, notesId: 0, notesAbort: null,
        status: page.querySelector("[data-personal-map-status]"), retry: page.querySelector("[data-personal-map-retry]"),
        favoriteStatus: page.querySelector("[data-country-favorite-status]"), notesContent: page.querySelector("[data-country-notes-content]"),
    };
    signal.addEventListener("abort", () => {state.notesId += 1; state.notesAbort?.abort();}, {once: true});
    state.retry.addEventListener("click", () => loadPersonalData(controller), {signal});
    page.querySelector("[data-favorite-jump]").addEventListener("change", event => {
        if (event.target.value) selectCountry(controller, event.target.value, {focusDrawer: true});
        event.target.value = "";
    }, {signal});
    state.notesContent.addEventListener("click", event => {
        if (event.target.closest("[data-country-notes-retry]")) loadCountryNotes(controller, {retry: true});
    }, {signal});
    page.querySelector("[data-country-favorite]").addEventListener("click", async () => {
        const code = controller.selectedCode;
        if (!state.ready || !code || state.favoritePending.has(code)) return;
        state.favoritePending.add(code);
        state.favoriteStatus.textContent = "Saving…";
        updatePersonalControls(controller);
        try {
            const result = await post(controller, page.dataset.favoriteUrlTemplate.replace("COUNTRY_CODE", encodeURIComponent(code)), {favorite: state.favorites.has(code) ? "0" : "1"});
            if (!isAlive(controller)) return;
            if (result.favorite) state.favorites.add(code);
            else state.favorites.delete(code);
            if (controller.selectedCode === code) state.favoriteStatus.textContent = "";
        } catch (error) {
            if (error.name !== "AbortError" && isAlive(controller) && controller.selectedCode === code) state.favoriteStatus.textContent = "Could not save the favorite. Try again.";
        } finally {
            state.favoritePending.delete(code);
            updatePersonalControls(controller);
        }
    }, {signal});
    page.querySelector("[data-active-preset]").addEventListener("change", async event => {
        const id = event.target.value;
        state.activating = true;
        state.status.textContent = "Saving active preset…";
        updatePersonalControls(controller);
        try {
            const url = id ? page.dataset.presetActivateUrlTemplate.replace("00000000-0000-0000-0000-000000000000", id) : page.dataset.presetClearUrl;
            const snapshot = await post(controller, url, {});
            if (!isAlive(controller)) return;
            state.activePreset = snapshot.active_preset;
            state.presets = snapshot.presets;
            state.colors = validColors(snapshot);
            state.defaultColor = snapshot.default_color;
            state.status.textContent = id ? "Preset colors are active." : "Preset colors are off.";
        } catch (error) {
            if (error.name !== "AbortError" && isAlive(controller)) state.status.textContent = "Could not change the preset. Try again.";
        } finally {
            state.activating = false;
            updatePersonalControls(controller);
        }
    }, {signal});
    loadPersonalData(controller);
}

export function registerPresetEditor() {
    if (editorRegistered) return;
    editorRegistered = true;
    document.addEventListener("click", event => {
        const button = event.target.closest("[data-preset-add-country]");
        if (!button) return;
        event.preventDefault();
        const editor = button.closest("[data-preset-editor]");
        const total = editor.querySelector('[name="colors-TOTAL_FORMS"]');
        const index = Number(total.value);
        if (index >= 238) return;
        const rows = editor.querySelector("[data-preset-rows]");
        rows.insertAdjacentHTML("beforeend", editor.querySelector("[data-preset-row-template]").innerHTML.replaceAll("__prefix__", String(index)));
        total.value = index + 1;
        rows.lastElementChild.querySelector("select")?.focus();
    });
}
