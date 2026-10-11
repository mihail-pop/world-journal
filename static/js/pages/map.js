import { countryFillExpression } from "./country_paint.js";
import { getCountryFeed, prioritizeCountryFeed, rememberCountryFeed } from "../news_cache.js";
import { basemapFeaturePreferences } from "./basemap_features.js";
import { factsSelectionChanged, initializeCountryFacts, loadCountryOverview } from "./map_facts.js";
import { applyPersonalLayers, initializePersonalMap, loadCountryNotes, loadPersonalData, personalSelectionChanged } from "./map_personal.js";
import { initializePresetMap, selectPresetCountry, syncPresetEditor } from "./preset_map_editor.js";
import {
    AttributionControl,
    Map as MapLibreMap,
    NavigationControl,
} from "../../vendor/maplibre-gl/maplibre-gl.mjs";
import {
    clearSavedMapViewport,
    MAP_VIEWPORT_STORAGE_KEY,
    MAP_BOOLEAN_PREFERENCES,
    readMapPreferences,
    writeMapPreferences,
} from "../map_preferences.js";

const WORLD_CAMERA = { center: [8, 18], zoom: 1.35 };
const SOURCE_ID = "world-journal-countries";
const CENTROID_SOURCE_ID = "world-journal-country-centroids";
const CAPITAL_SOURCE_ID = "world-journal-capitals";
const FAVORITE_ICON_ID = "world-journal-favorite-heart";
const COUNTRY_NEWS_DELAY_MS = 300;
const LAYERS = {
    simpleBackground: "world-journal-simple-background",
    fill: "world-journal-country-fill",
    outline: "world-journal-country-outline",
    favoriteMarkers: "world-journal-country-favorites",
    smallMarker: "world-journal-country-small-marker",
    hitTarget: "world-journal-country-hit-target",
    countryNames: "world-journal-country-names",
    capitalMarkers: "world-journal-capital-markers",
    capitalNames: "world-journal-capital-names",
};

let lifecycleRegistered = false;
let activeController = null;

function readViewport() {
    try {
        const value = JSON.parse(localStorage.getItem(MAP_VIEWPORT_STORAGE_KEY));
        if (
            Array.isArray(value?.center)
            && value.center.length === 2
            && value.center.every(Number.isFinite)
            && Number.isFinite(value.zoom)
        ) {
            return value;
        }
    } catch (error) {
        return null;
    }
    return null;
}

function saveViewport(map) {
    const center = map.getCenter();
    try {
        localStorage.setItem(MAP_VIEWPORT_STORAGE_KEY, JSON.stringify({
            center: [center.lng, center.lat],
            zoom: map.getZoom(),
        }));
    } catch (error) {
        // The map remains usable when browser storage is unavailable.
    }
}

function getThemeColor(variable) {
    return getComputedStyle(document.documentElement).getPropertyValue(variable).trim();
}

function updateLayerTheme(controller) {
    const { map } = controller;
    if (!map || !controller.layersInstalled) {
        return;
    }
    const background = getThemeColor("--bg-primary");
    const countryFill = getThemeColor("--bg-quaternary");
    const countryOutline = getThemeColor("--text-primary");
    const hover = getThemeColor("--special-color");
    const selected = getThemeColor("--text-secondary");
    const theme = {fill: countryFill, accent: hover, opacity: controller.preferences.terrain ? .22 : .72};
    const key = JSON.stringify([theme, background, countryOutline, selected, getThemeColor("--bg-tertiary")]);
    if (controller.paintThemeKey === key) return;
    controller.paintThemeKey = key;
    controller.countryPaintTheme = theme;
    const hovered = ["boolean", ["feature-state", "hover"], false];
    const selectedState = ["boolean", ["feature-state", "selected"], false];
    map.setPaintProperty(LAYERS.simpleBackground, "background-color", getThemeColor("--bg-tertiary"));
    map.setPaintProperty(LAYERS.outline, "line-color", ["case", selectedState, selected, hovered, hover, countryOutline]);
    map.setPaintProperty(LAYERS.outline, "line-width", ["case", selectedState, 3.5, hovered, 2, .8]);
    map.setPaintProperty(LAYERS.outline, "line-opacity", ["case", ["any", selectedState, hovered], 1, .62]);
    map.setPaintProperty(LAYERS.smallMarker, "circle-color", ["coalesce", ["feature-state", "presetColor"], hover]);
    map.setPaintProperty(LAYERS.smallMarker, "circle-stroke-color", selected);
    map.setPaintProperty(LAYERS.countryNames, "text-color", selected);
    map.setPaintProperty(LAYERS.countryNames, "text-halo-color", background);
    map.setPaintProperty(LAYERS.capitalMarkers, "circle-color", selected);
    map.setPaintProperty(LAYERS.capitalMarkers, "circle-stroke-color", background);
    map.setPaintProperty(LAYERS.capitalNames, "text-color", selected);
    map.setPaintProperty(LAYERS.capitalNames, "text-halo-color", background);
    applyPersonalLayers(controller);
    if (controller.usingFallbackStyle && map.getLayer("world-journal-background")) {
        map.setPaintProperty("world-journal-background", "background-color", background);
    }
}

function selectedCodeFromUrl(countriesByCode) {
    const requestedCode = new URL(window.location.href).searchParams.get("country");
    if (!requestedCode) {
        return { code: null, unsupported: null };
    }
    const normalizedCode = requestedCode.trim().toUpperCase();
    return countriesByCode.has(normalizedCode)
        ? { code: normalizedCode, unsupported: null }
        : { code: null, unsupported: normalizedCode };
}

function updateHistory(code) {
    const url = new URL(window.location.href);
    url.searchParams.delete("section");
    if (code) {
        url.searchParams.set("country", code);
    } else {
        url.searchParams.delete("country");
    }
    history.pushState({ worldJournalCountry: code }, "", url);
    document.dispatchEvent(new CustomEvent("world-journal:location-change"));
}

function setSelectedCountry(controller, code) {
    const { map, selectedCode } = controller;
    // Selection must use the same paint-only path as hover. These updates merge
    // only the selected flag, leaving any independent hover state intact.
    // Preset mode clears selection before the renderer is created on a fresh
    // page load. Keep the logical selection current even without a map yet.
    if (map?.getSource(SOURCE_ID)) {
        if (selectedCode && selectedCode !== code) {
            map.setFeatureState({ source: SOURCE_ID, id: selectedCode }, { selected: false });
        }
        if (code) {
            map.setFeatureState({ source: SOURCE_ID, id: code }, { selected: true });
        }
    }
    controller.selectedCode = code;
}

function setHoveredCountry(controller, code) {
    code = controller.countriesByCode.has(code) ? code : null;
    if (code === controller.hoveredCode) {
        return;
    }
    const { map, hoveredCode } = controller;
    // Paint state changes coalesce in the renderer's next frame. Changing layer
    // filters instead would rebuild GeoJSON tiles asynchronously on every hover.
    if (map.getSource(SOURCE_ID)) {
        if (hoveredCode) {
            map.setFeatureState({ source: SOURCE_ID, id: hoveredCode }, { hover: false });
        }
        if (code) {
            map.setFeatureState({ source: SOURCE_ID, id: code }, { hover: true });
        }
    }
    controller.hoveredCode = code;
    map.getCanvas().style.cursor = code ? "pointer" : "";
}

function cancelHoverFrame(controller) {
    if (controller.hoverFrame !== null) {
        cancelAnimationFrame(controller.hoverFrame);
        controller.hoverFrame = null;
    }
}

function clearHover(controller) {
    cancelHoverFrame(controller);
    controller.hoverPoint = null;
    setHoveredCountry(controller, null);
}

function scheduleHoverUpdate(controller) {
    if (
        activeController !== controller || controller.abortController.signal.aborted || controller.suspended
        || controller.hoverFrame !== null || !controller.hoverPoint || !controller.layersInstalled
    ) {
        return;
    }
    controller.hoverFrame = requestAnimationFrame(() => {
        controller.hoverFrame = null;
        if (
            activeController !== controller || controller.abortController.signal.aborted || controller.suspended
            || !controller.hoverPoint || !controller.layersInstalled
        ) {
            return;
        }
        // Read the latest point, not the point from the event that queued this
        // frame. Intermediate mouse moves never become a backlog of highlights.
        if (controller.map.isMoving()) {
            setHoveredCountry(controller, null);
            return;
        }
        setHoveredCountry(controller, queryCountryCode(controller, controller.hoverPoint));
    });
}

function drawerPadding() {
    const drawer = document.querySelector("[data-country-drawer]");
    const workspace = document.querySelector(".map-workspace");
    if (!drawer || drawer.hidden) return {top: 56, right: 56, bottom: 56, left: 56};
    if (window.matchMedia("(max-width: 46rem)").matches) {
        const drawerHeight = drawer && !drawer.hidden ? drawer.offsetHeight : 240;
        const playerOffset = Number.parseFloat(document.documentElement.style.getPropertyValue("--persistent-player-map-offset")) || 0;
        const availableHeight = workspace?.clientHeight || window.innerHeight;
        return { top: 56, right: 24, bottom: Math.min(drawerHeight + playerOffset + 24, availableHeight * .65), left: 24 };
    }
    const drawerWidth = drawer?.offsetWidth || 480;
    return { top: 56, right: Math.min(drawerWidth + 48, (workspace?.clientWidth || window.innerWidth) * .6), bottom: 56, left: 56 };
}

function focusCountry(controller, country, animate = true) {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    controller.map.fitBounds(country.bounds, {
        padding: drawerPadding(),
        retainPadding: false,
        maxZoom: country.small ? 7 : 5.5,
        duration: animate && !reducedMotion ? 650 : 0,
    });
}

function cancelCountryNews(controller, { abort = false } = {}) {
    controller.newsRequestId += 1;
    window.clearTimeout(controller.newsTimer);
    controller.newsTimer = null;
    controller.pendingNews = null;
    // Disconnecting a browser request does not stop Django's feed work. Let a
    // started request finish, but invalidate its result when selection changes.
    if (abort) {
        controller.newsAbortController?.abort();
        controller.newsAbortController = null;
    }
}

function cancelCountryVideos(controller) {
    controller.videoRequestId += 1;
    controller.videoAbortController?.abort();
    controller.videoAbortController = null;
}

function showNewsMessage(controller, message, { retry = false } = {}) {
    controller.newsContent.replaceChildren();
    const messageElement = document.createElement("p");
    messageElement.className = "country-news-message";
    messageElement.textContent = message;
    controller.newsContent.append(messageElement);
    if (retry) {
        const retryButton = document.createElement("button");
        retryButton.type = "button";
        retryButton.className = "news-retry";
        retryButton.dataset.newsRetry = "";
        retryButton.textContent = "Retry";
        controller.newsContent.append(retryButton);
    }
}

function applyNewsFilter(controller, filter) {
    for (const button of controller.newsContent.querySelectorAll("[data-news-filter]")) {
        button.setAttribute("aria-pressed", String(button.dataset.newsFilter === filter));
    }
    for (const section of controller.newsContent.querySelectorAll("[data-news-section]")) {
        section.hidden = filter !== "all" && section.dataset.newsSection !== filter;
    }
}

function loadCountryNews(controller, code, countryName, { retryFailed = false } = {}) {
    cancelCountryNews(controller);
    prioritizeCountryFeed(code);
    const cached = getCountryFeed(code, "articles");
    if (cached) {
        renderCachedNews(controller, code, cached);
        if (!retryFailed) return;
    }
    controller.newsContent.setAttribute("aria-busy", "true");
    if (!cached) showNewsMessage(controller, controller.newsAbortController
        ? `Loading headlines for ${countryName}; waiting for the previous news request to finish…`
        : `Loading current English-language headlines for ${countryName}…`);
    controller.pendingNews = { code, countryName, retryFailed, requestId: controller.newsRequestId };
    // Coalesce quick clicks before contacting the server. A pending selection
    // replaces the previous one, so there is never a queue of country requests.
    controller.newsTimer = window.setTimeout(() => {
        controller.newsTimer = null;
        startPendingCountryNews(controller);
    }, COUNTRY_NEWS_DELAY_MS);
}

function renderCachedNews(controller, code, entry) {
    if (!entry) return;
    let filter = controller.newsContent.dataset.loadedCountry === code
        ? controller.newsContent.querySelector('[data-news-filter][aria-pressed="true"]')?.dataset.newsFilter || "all"
        : "all";
    controller.newsContent.innerHTML = entry.markup;
    controller.newsContent.dataset.loadedCountry = code;
    controller.newsContent.setAttribute("aria-busy", String(entry.pending));
    window.htmx?.process(controller.newsContent);
    if (![...controller.newsContent.querySelectorAll("[data-news-filter]")].some(button => button.dataset.newsFilter === filter)) {
        filter = "all";
    }
    applyNewsFilter(controller, filter);
}

function renderCachedVideos(controller, code, entry) {
    if (!entry) return;
    controller.videoContent.innerHTML = entry.markup;
    controller.videoContent.dataset.loadedCountry = code;
    controller.videoContent.setAttribute("aria-busy", String(entry.pending));
    window.htmx?.process(controller.videoContent);
}

function startPendingCountryNews(controller) {
    if (
        activeController !== controller
        || controller.abortController.signal.aborted
        || controller.newsTimer !== null
        || controller.newsAbortController
        || !controller.pendingNews
    ) {
        return;
    }
    const request = controller.pendingNews;
    controller.pendingNews = null;
    if (controller.selectedCode === request.code && controller.newsRequestId === request.requestId) {
        fetchCountryNews(controller, request);
    }
}

async function fetchCountryNews(controller, { code, countryName, retryFailed, requestId }) {
    const requestedAt = Date.now();
    const abortController = new AbortController();
    controller.newsAbortController = abortController;
    controller.newsContent.setAttribute("aria-busy", "true");
    if (!getCountryFeed(code, "articles")) showNewsMessage(controller, `Preparing headlines for ${countryName}…`);
    const url = new URL(
        controller.newsUrlTemplate.replace("COUNTRY_CODE", encodeURIComponent(code)),
        window.location.origin,
    );
    if (retryFailed) {
        url.searchParams.set("refresh", "failed");
    }

    try {
        const response = await fetch(url, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
            signal: abortController.signal,
        });
        if (!response.ok) {
            throw new Error(`${url} returned HTTP ${response.status}`);
        }
        const markup = await response.text();
        if (
            activeController !== controller
            || controller.selectedCode !== code
            || controller.newsRequestId !== requestId
        ) {
            return;
        }
        const entry = rememberCountryFeed(code, "articles", markup, { requestedAt, version: response.headers.get("X-Feed-Version"), notify: false });
        renderCachedNews(controller, code, entry);
    } catch (error) {
        if (error.name === "AbortError" || activeController !== controller || controller.newsRequestId !== requestId) {
            return;
        }
        controller.newsContent.setAttribute("aria-busy", "false");
        const cached = getCountryFeed(code, "articles");
        if (cached) renderCachedNews(controller, code, cached);
        else showNewsMessage(controller, "Current news could not be loaded.", { retry: true });
        console.error("World Journal country news request failed", error);
    } finally {
        if (controller.newsAbortController === abortController) {
            controller.newsAbortController = null;
        }
        startPendingCountryNews(controller);
    }
}

function showVideoMessage(controller, message, { retry = false } = {}) {
    controller.videoContent.replaceChildren();
    const messageElement = document.createElement("p");
    messageElement.className = "country-news-message";
    messageElement.textContent = message;
    controller.videoContent.append(messageElement);
    if (retry) {
        const retryButton = document.createElement("button");
        retryButton.type = "button";
        retryButton.className = "news-retry";
        retryButton.dataset.videoRetry = "";
        retryButton.textContent = "Retry";
        controller.videoContent.append(retryButton);
    }
}

async function loadCountryVideos(controller, code, countryName, { retryFailed = false } = {}) {
    cancelCountryVideos(controller);
    prioritizeCountryFeed(code);
    const cached = getCountryFeed(code, "videos");
    if (cached) {
        renderCachedVideos(controller, code, cached);
        if (!retryFailed) return;
    }
    const requestId = controller.videoRequestId;
    const requestedAt = Date.now();
    const abortController = new AbortController();
    controller.videoAbortController = abortController;
    controller.videoContent.setAttribute("aria-busy", "true");
    if (!cached) showVideoMessage(controller, `Preparing recent videos for ${countryName}…`);
    const url = new URL(
        controller.videoUrlTemplate.replace("COUNTRY_CODE", encodeURIComponent(code)),
        window.location.origin,
    );
    if (retryFailed) {
        url.searchParams.set("refresh", "failed");
    }

    try {
        const response = await fetch(url, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
            signal: abortController.signal,
        });
        if (!response.ok) {
            throw new Error(`${url} returned HTTP ${response.status}`);
        }
        const markup = await response.text();
        if (
            activeController !== controller
            || controller.selectedCode !== code
            || controller.videoRequestId !== requestId
        ) {
            return;
        }
        const entry = rememberCountryFeed(code, "videos", markup, { requestedAt, version: response.headers.get("X-Feed-Version"), notify: false });
        renderCachedVideos(controller, code, entry);
    } catch (error) {
        if (error.name === "AbortError" || activeController !== controller || controller.videoRequestId !== requestId) {
            return;
        }
        controller.videoContent.setAttribute("aria-busy", "false");
        const retained = getCountryFeed(code, "videos");
        if (retained) renderCachedVideos(controller, code, retained);
        else showVideoMessage(controller, "Current videos could not be loaded.", { retry: true });
        console.error("World Journal country videos request failed", error);
    } finally {
        if (controller.videoRequestId === requestId) {
            controller.videoAbortController = null;
        }
    }
}

function selectCountrySection(controller, section, { focus = false } = {}) {
    if (section === "notes") loadCountryNotes(controller);
    if (section === "overview") loadCountryOverview(controller);
    for (const button of controller.page.querySelectorAll("[data-country-section]")) {
        const selected = button.dataset.countrySection === section;
        button.setAttribute("aria-selected", String(selected));
        button.tabIndex = selected ? 0 : -1;
        if (selected && focus) {
            button.focus();
        }
    }
    for (const panel of controller.page.querySelectorAll("[data-country-section-panel]")) {
        panel.hidden = panel.dataset.countrySectionPanel !== section;
    }
    if (
        section === "videos"
        && controller.selectedCode
        && controller.videoContent.dataset.loadedCountry !== controller.selectedCode
        && !controller.videoAbortController
    ) {
        const country = controller.countriesByCode.get(controller.selectedCode);
        loadCountryVideos(controller, controller.selectedCode, country.name);
    }
}

function renderSelection(controller, code, { fit = true, focusDrawer = false } = {}) {
    const drawer = controller.page.querySelector("[data-country-drawer]");
    if (code && code === controller.selectedCode && !drawer.hidden) {
        // Re-clicking the selected country should keep loaded tabs and pending
        // requests intact. Initial/deep-link rendering still runs for a hidden drawer.
        const requestedSection = new URL(window.location.href).searchParams.get("section");
        if (["overview", "notes"].includes(requestedSection)) selectCountrySection(controller, requestedSection);
        if (fit) focusCountry(controller, controller.countriesByCode.get(code));
        if (focusDrawer) drawer.focus({ preventScroll: true });
        return;
    }
    setSelectedCountry(controller, code);
    personalSelectionChanged(controller);
    factsSelectionChanged(controller);

    if (!code) {
        cancelCountryNews(controller);
        controller.newsContent.replaceChildren();
        controller.newsContent.setAttribute("aria-busy", "false");
        cancelCountryVideos(controller);
        drawer.hidden = true;
        controller.page.classList.remove("has-country-drawer");
        return;
    }

    const country = controller.countriesByCode.get(code);
    cancelCountryVideos(controller);
    controller.videoContent.replaceChildren();
    delete controller.videoContent.dataset.loadedCountry;
    controller.videoContent.setAttribute("aria-busy", "false");
    selectCountrySection(controller, "articles");
    const flagImage = controller.page.querySelector("[data-country-flag]");
    const flagFallback = controller.page.querySelector("[data-country-flag-fallback]");
    flagFallback.textContent = country.flag;
    flagFallback.hidden = false;
    flagImage.hidden = true;
    flagImage.onload = () => {
        flagImage.hidden = false;
        flagFallback.hidden = true;
    };
    flagImage.onerror = () => {
        flagImage.hidden = true;
        flagFallback.hidden = false;
    };
    flagImage.src = `https://flagcdn.com/${country.iso_a2.toLowerCase()}.svg`;
    controller.page.querySelector("[data-country-name]").textContent = country.name;
    controller.page.querySelector("[data-country-journal-link]").href = `/journal/?country=${encodeURIComponent(code)}`;
    controller.page.querySelector("[data-country-region]").textContent = country.region;
    controller.page.querySelector("[data-country-subregion]").textContent = country.subregion;
    drawer.hidden = false;
    controller.page.classList.add("has-country-drawer");
    loadCountryNews(controller, code, country.name);
    const requestedSection = new URL(window.location.href).searchParams.get("section");
    if (["overview", "notes"].includes(requestedSection)) selectCountrySection(controller, requestedSection);
    if (fit) {
        focusCountry(controller, country);
    }
    if (focusDrawer) {
        drawer.focus({ preventScroll: true });
    }
}

function selectCountry(controller, code, options = {}) {
    if (!controller.countriesByCode.has(code)) {
        return;
    }
    if (selectPresetCountry(controller, code)) return;
    if (options.pushHistory !== false && code !== controller.selectedCode) {
        updateHistory(code);
    }
    renderSelection(controller, code, options);
}

function closeCountry(controller, { pushHistory = true, focusMap = true } = {}) {
    if (controller.presetEditor?.active && pushHistory) return;
    if (pushHistory && (controller.selectedCode || new URL(window.location.href).searchParams.has("country"))) {
        updateHistory(null);
    }
    renderSelection(controller, null, { fit: false });
    if (focusMap) {
        controller.container.focus({ preventScroll: true });
    }
}

function queryCountryCode(controller, point) {
    const layers = [LAYERS.favoriteMarkers, LAYERS.hitTarget, LAYERS.fill].filter((layerId) => controller.map.getLayer(layerId));
    if (!layers.length) {
        return null;
    }
    return controller.map.queryRenderedFeatures(point, { layers })[0]?.properties?.iso_a2 ?? null;
}

function isApplicationLayer(layer) {
    return layer.id.startsWith("world-journal-");
}

function serializedLayerDefinition(layer) {
    return `${layer.id} ${layer["source-layer"] ?? ""} ${JSON.stringify(layer.filter ?? [])}`.toLowerCase();
}

function isBasemapCountryLabel(layer) {
    const definition = serializedLayerDefinition(layer);
    return layer.type === "symbol"
        && (definition.includes("label_country") || (
            layer["source-layer"] === "place" && definition.includes("country")
        ));
}

function isBasemapCapitalLabel(layer) {
    const definition = serializedLayerDefinition(layer);
    return layer.type === "symbol"
        && (definition.includes("capital") || (
            layer["source-layer"] === "place" && definition.includes("adm0cap")
        ));
}

function originalVisibility(controller, layer) {
    if (!controller.basemapVisibility.has(layer.id)) {
        controller.basemapVisibility.set(
            layer.id,
            controller.map.getLayoutProperty(layer.id, "visibility") ?? "visible",
        );
    }
    return controller.basemapVisibility.get(layer.id);
}

function applyBasemapPreferences(controller) {
    for (const layer of controller.basemapLayers) {
        const visibility = originalVisibility(controller, layer);
        const hidden = !controller.preferences.terrain
            || isBasemapCountryLabel(layer)
            || isBasemapCapitalLabel(layer)
            || controller.basemapFeatureGroups.get(layer.id).some(key => !controller.preferences[key]);
        // Hidden terrain must stop drawing and requesting tiles. Changing every
        // opacity left all its geometry active, including while invisible.
        setLayerVisibility(controller.map, layer.id, !hidden && visibility !== "none");
    }
}

function setLayerVisibility(map, layerId, visible) {
    if (map.getLayer(layerId)) {
        const visibility = visible ? "visible" : "none";
        if ((map.getLayoutProperty(layerId, "visibility") ?? "visible") !== visibility) {
            map.setLayoutProperty(layerId, "visibility", visibility);
        }
    }
}

function updateControls(controller) {
    for (const input of controller.page.querySelectorAll("[data-map-preference]")) {
        const key = input.dataset.mapPreference;
        input.checked = Boolean(controller.preferences[key]);
    }
}

function applyPreferences(controller) {
    updateControls(controller);
    if (!controller.layersInstalled) {
        return;
    }
    applyBasemapPreferences(controller);
    setLayerVisibility(controller.map, LAYERS.simpleBackground, !controller.preferences.terrain);
    setLayerVisibility(
        controller.map,
        LAYERS.countryNames,
        controller.preferences.countryNames,
    );
    const showCapitals = controller.preferences.capitalNames;
    setLayerVisibility(controller.map, LAYERS.capitalMarkers, showCapitals);
    setLayerVisibility(controller.map, LAYERS.capitalNames, showCapitals);
    setLayerVisibility(controller.map, LAYERS.smallMarker, controller.preferences.smallCountryMarkers);
    updateLayerTheme(controller);
    const styleLayers = controller.basemapLayers;
    const isVisible = (layerId) => controller.map.getLayoutProperty(layerId, "visibility") !== "none";
    const basemapCountryLabels = styleLayers.filter((layer) => (
        !isApplicationLayer(layer) && isBasemapCountryLabel(layer)
    ));
    const basemapCapitalLabels = styleLayers.filter((layer) => (
        !isApplicationLayer(layer) && isBasemapCapitalLabel(layer)
    ));
    const visibleBasemapLayers = styleLayers.filter((layer) => (
        isVisible(layer.id)
    ));
    controller.page.dataset.appliedCountryNames = String(isVisible(LAYERS.countryNames));
    controller.page.dataset.appliedCapitalNames = String(
        isVisible(LAYERS.capitalMarkers) && isVisible(LAYERS.capitalNames),
    );
    controller.page.dataset.appliedSimpleMode = String(
        !controller.preferences.terrain
            && isVisible(LAYERS.simpleBackground)
            && visibleBasemapLayers.length === 0,
    );
    controller.page.dataset.visibleBasemapLayers = String(visibleBasemapLayers.length);
    controller.page.dataset.visibleBasemapCountryLabels = String(
        basemapCountryLabels.filter((layer) => isVisible(layer.id)).length,
    );
    controller.page.dataset.visibleBasemapCapitalLabels = String(
        basemapCapitalLabels.filter((layer) => isVisible(layer.id)).length,
    );
    controller.page.dataset.applicationLayerCount = String(
        Object.values(LAYERS).filter(id => controller.map.getLayer(id)).length,
    );
}

function addLayer(controller, definition, beforeId) {
    for (const property of Object.keys(definition.paint ?? {})) {
        if (property.endsWith("-color") || property.endsWith("-opacity")) definition.paint[`${property}-transition`] = {duration: 0, delay: 0};
    }
    if (!controller.map.getLayer(definition.id)) {
        controller.map.addLayer(definition, beforeId);
    }
}

function installCountryLayers(controller) {
    const { map } = controller;
    // A style can recreate layers while retaining the GeoJSON source itself.
    controller.appliedFavorites = null;
    // Capture provider definitions once per style, before adding our GeoJSON.
    // Preference toggles only need these IDs/label rules, not whole style copies.
    controller.basemapLayers = (map.getStyle().layers ?? []).filter(layer => !isApplicationLayer(layer));
    controller.basemapFeatureGroups = new Map(controller.basemapLayers.map(layer => (
        [layer.id, basemapFeaturePreferences(layer)]
    )));
    const firstBasemapLayer = controller.basemapLayers[0]?.id;
    if (!map.getSource(SOURCE_ID)) {
        // Restore MapLibre's previous subpixel tolerance. Keep the source's
        // normal zoom range and detailed geometry, not a coarse world tile.
        map.addSource(SOURCE_ID, { type: "geojson", data: controller.geometry, promoteId: "iso_a2" });
    }
    if (!map.getSource(CENTROID_SOURCE_ID)) {
        map.addSource(CENTROID_SOURCE_ID, { type: "geojson", data: controller.centroids, promoteId: "iso_a2" });
    }
    if (!map.getSource(CAPITAL_SOURCE_ID)) {
        map.addSource(CAPITAL_SOURCE_ID, { type: "geojson", data: controller.capitals });
    }
    addLayer(controller, {
        id: LAYERS.simpleBackground,
        type: "background",
        layout: { visibility: "none" },
        paint: { "background-color": "#151f2e" },
    }, firstBasemapLayer);
    addLayer(controller, { id: LAYERS.fill, type: "fill", source: SOURCE_ID, paint: { "fill-color": countryFillExpression(), "fill-opacity": 1 } });
    addLayer(controller, { id: LAYERS.outline, type: "line", source: SOURCE_ID, paint: { "line-color": "#8596a5", "line-opacity": .62, "line-width": .8, "line-width-transition": {duration: 0, delay: 0} } });
    if (controller.favoriteIcon) {
        if (!map.hasImage(FAVORITE_ICON_ID)) map.addImage(FAVORITE_ICON_ID, controller.favoriteIcon, {pixelRatio: 2});
        addLayer(controller, {
            id: LAYERS.favoriteMarkers, type: "symbol", source: CENTROID_SOURCE_ID,
            filter: ["in", ["get", "iso_a2"], ["literal", []]],
            layout: {
                "icon-image": FAVORITE_ICON_ID, "icon-size": .9, "icon-offset": [0, -12],
                "icon-allow-overlap": true, "icon-ignore-placement": true,
            },
        });
    }
    addLayer(controller, {
        id: LAYERS.smallMarker,
        type: "circle",
        source: CENTROID_SOURCE_ID,
        filter: ["==", ["get", "small"], true],
        layout: { visibility: "none" },
        paint: { "circle-color": "#00bfff", "circle-radius": 3.5, "circle-stroke-color": "#a8b5c4", "circle-stroke-width": 1.5 },
    });
    addLayer(controller, {
        id: LAYERS.hitTarget,
        type: "circle",
        source: CENTROID_SOURCE_ID,
        paint: { "circle-color": "#00bfff", "circle-radius": 11, "circle-opacity": 0.01 },
    });
    addLayer(controller, {
        id: LAYERS.countryNames,
        type: "symbol",
        source: CENTROID_SOURCE_ID,
        minzoom: 1,
        maxzoom: 8,
        layout: {
            "symbol-avoid-edges": true,
            "text-field": ["get", "name"],
            "text-font": ["Noto Sans Bold"],
            "text-size": ["interpolate", ["linear"], ["zoom"], 1, 9, 5, 14],
            "text-max-width": 7,
        },
        paint: { "text-color": "#a8b5c4", "text-halo-color": "#0b1622", "text-halo-width": 1.25 },
    });
    addLayer(controller, {
        id: LAYERS.capitalMarkers,
        type: "circle",
        source: CAPITAL_SOURCE_ID,
        minzoom: 2.5,
        layout: { visibility: "none" },
        paint: { "circle-color": "#a8b5c4", "circle-radius": 2.5, "circle-stroke-color": "#0b1622", "circle-stroke-width": 1 },
    });
    addLayer(controller, {
        id: LAYERS.capitalNames,
        type: "symbol",
        source: CAPITAL_SOURCE_ID,
        minzoom: 2.5,
        layout: {
            visibility: "none",
            "symbol-avoid-edges": true,
            "text-field": ["get", "name"],
            "text-font": ["Noto Sans Regular"],
            "text-size": ["interpolate", ["linear"], ["zoom"], 2.5, 9, 7, 12],
            "text-anchor": "top",
            "text-offset": [0, 0.55],
            "text-max-width": 8,
            "text-optional": true,
        },
        paint: { "text-color": "#a8b5c4", "text-halo-color": "#0b1622", "text-halo-width": 1.2 },
    });
    controller.layersInstalled = true;
    if (controller.hoveredCode) {
        // A replacement basemap can recreate the source and lose feature state.
        map.setFeatureState({ source: SOURCE_ID, id: controller.hoveredCode }, { hover: true });
    }
    applyPreferences(controller);
    setSelectedCountry(controller, controller.selectedCode);
    controller.status.hidden = true;
    scheduleHoverUpdate(controller);
}

function createCentroids(countries) {
    return {
        type: "FeatureCollection",
        features: countries.map((country) => ({
            type: "Feature",
            id: country.iso_a2,
            properties: { iso_a2: country.iso_a2, name: country.name, small: country.small },
            geometry: { type: "Point", coordinates: country.centroid },
        })),
    };
}

function initialCamera(selectedCountry, homeCountry, savedViewport) {
    const country = selectedCountry ?? homeCountry;
    if (country) {
        return { center: country.centroid, zoom: country.small ? 6 : 3.2 };
    }
    return savedViewport ?? WORLD_CAMERA;
}

function showNotice(controller, message) {
    controller.notice.textContent = message;
    controller.notice.hidden = !message;
}

function applyProviderFallback(controller) {
    if (controller.usingFallbackStyle || controller.layersInstalled || activeController !== controller) {
        return;
    }
    controller.usingFallbackStyle = true;
    controller.layersInstalled = false;
    controller.status.textContent = "Map provider unavailable. Showing bundled country boundaries.";
    controller.map.setStyle({
        version: 8,
        glyphs: controller.glyphsUrl,
        sources: {},
        layers: [{ id: "world-journal-background", type: "background", paint: { "background-color": "#0b1622" } }],
    });
}

function createMap(controller, styleUrl) {
    const requested = controller.presetEditor?.active ? {code: null, unsupported: null} : selectedCodeFromUrl(controller.countriesByCode);
    controller.selectedCode = requested.code;
    if (requested.unsupported) {
        showNotice(controller, `Country code ${requested.unsupported} is not available in the bundled dataset.`);
    }
    const selectedCountry = requested.code ? controller.countriesByCode.get(requested.code) : null;
    const homeCountry = controller.preferences.homeCountry
        ? controller.countriesByCode.get(controller.preferences.homeCountry)
        : null;
    const savedViewport = readViewport();
    controller.page.dataset.initialCameraSource = selectedCountry
        ? "country-query"
        : homeCountry
            ? "home-country"
            : savedViewport
                ? "saved-viewport"
                : "world";
    const camera = initialCamera(selectedCountry, homeCountry, savedViewport);
    const map = new MapLibreMap({
        container: controller.container,
        style: styleUrl,
        center: camera.center,
        zoom: camera.zoom,
        renderWorldCopies: true,
        fadeDuration: 300,
        maxTileCacheZoomLevels: 7,
        attributionControl: false,
    });
    controller.map = map;
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new AttributionControl({
        compact: true,
    }), "bottom-left");
    const collapseAttribution = () => {
        const attribution = controller.container.querySelector(".maplibregl-ctrl-attrib");
        attribution?.removeAttribute("open");
        attribution?.classList.remove("maplibregl-compact-show");
        // MapLibre rebuilds provider attribution links as sources change.
        for (const link of attribution?.querySelectorAll('a[target="_blank"]') ?? []) {
            link.relList.add("noopener", "noreferrer");
        }
    };
    collapseAttribution();
    const attribution = controller.container.querySelector(".maplibregl-ctrl-attrib");
    if (attribution) {
        controller.attributionObserver = new MutationObserver(collapseAttribution);
        controller.attributionObserver.observe(attribution, { childList: true, subtree: true });
    }
    map.on("resize", collapseAttribution);
    map.on("idle", collapseAttribution);

    controller.fallbackTimer = window.setTimeout(() => applyProviderFallback(controller), 8000);
    map.on("style.load", () => {
        window.clearTimeout(controller.fallbackTimer);
        controller.layersInstalled = false;
        controller.basemapVisibility.clear();
        controller.paintThemeKey = null;
        installCountryLayers(controller);
        requestAnimationFrame(collapseAttribution);
    });
    map.on("error", () => {
        if (!controller.layersInstalled) {
            applyProviderFallback(controller);
        } else if (!controller.usingFallbackStyle) {
            showNotice(controller, "Some map-provider resources are unavailable; bundled country selection remains active.");
        }
    });
    map.on("movestart", () => {
        cancelHoverFrame(controller);
        setHoveredCountry(controller, null);
    });
    map.on("moveend", () => {
        saveViewport(map);
        scheduleHoverUpdate(controller);
    });
    // Recheck a stationary pointer once newly loaded tiles have been rendered.
    map.on("idle", () => scheduleHoverUpdate(controller));
    map.on("mousemove", (event) => {
        controller.hoverPoint = [event.point.x, event.point.y];
        scheduleHoverUpdate(controller);
    });
    map.on("click", (event) => {
        const code = queryCountryCode(controller, event.point);
        if (code) {
            selectCountry(controller, code, { fit: true, focusDrawer: true });
        }
    });
    map.getCanvas().addEventListener("mouseleave", () => clearHover(controller), { signal: controller.abortController.signal });
    window.addEventListener("blur", () => clearHover(controller), { signal: controller.abortController.signal });
    if (requested.code) {
        renderSelection(controller, requested.code, { fit: false });
    }
    // Fit synchronously before the asynchronous style/source load. Otherwise
    // startup requests tiles for the provisional camera, then a second set for
    // the fitted home country as soon as country layers are installed.
    const openingCountry = selectedCountry ?? homeCountry;
    if (openingCountry) focusCountry(controller, openingCountry, false);
}

function closeControlsPanel(controller, { restoreFocus = false } = {}) {
    if (controller.controlsPanel.hidden) {
        return;
    }
    controller.controlsPanel.hidden = true;
    controller.controlsToggle.setAttribute("aria-expanded", "false");
    if (restoreFocus) {
        controller.controlsToggle.focus();
    }
}

function updateHomeControls(controller) {
    const homeCountry = controller.preferences.homeCountry
        ? controller.countriesByCode.get(controller.preferences.homeCountry)
        : null;
    controller.homeButton.disabled = !homeCountry;
    controller.homeButton.title = homeCountry
        ? `View ${homeCountry.name}`
        : "Choose a home country in Settings";
    controller.homeSummary.textContent = homeCountry
        ? `Home country: ${homeCountry.name}`
        : "Home country is not configured.";
    updateControls(controller);
}

function initializeControls(controller) {
    updateHomeControls(controller);

    controller.controlsToggle.addEventListener("click", () => {
        const willOpen = controller.controlsPanel.hidden;
        controller.controlsPanel.hidden = !willOpen;
        controller.controlsToggle.setAttribute("aria-expanded", String(willOpen));
        if (willOpen) {
            controller.controlsPanel.querySelector("input:not(:disabled)")?.focus();
        }
    }, { signal: controller.abortController.signal });
    controller.toolbar.addEventListener("change", (event) => {
        const input = event.target.closest("[data-map-preference]");
        if (!input || input.disabled) {
            return;
        }
        const key = input.dataset.mapPreference;
        if (!MAP_BOOLEAN_PREFERENCES.includes(key)) return;
        controller.preferences = writeMapPreferences(
            { ...controller.preferences, [key]: input.checked },
            controller.countryCodes,
        );
    }, { signal: controller.abortController.signal });
    controller.homeButton.addEventListener("click", () => {
        const homeCountry = controller.countriesByCode.get(controller.preferences.homeCountry);
        if (!homeCountry) {
            return;
        }
        closeCountry(controller, { focusMap: false });
        focusCountry(controller, homeCountry);
    }, { signal: controller.abortController.signal });
    controller.worldButton.addEventListener("click", () => {
        closeCountry(controller, { focusMap: false });
        clearSavedMapViewport();
        const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        controller.map?.easeTo({ ...WORLD_CAMERA, padding: 0, duration: reducedMotion ? 0 : 650 });
    }, { signal: controller.abortController.signal });
    document.addEventListener("pointerdown", (event) => {
        if (controller.suspended) return;
        if (!controller.toolbar.contains(event.target)) {
            closeControlsPanel(controller);
        }
    }, { signal: controller.abortController.signal });
}

async function loadJson(url, signal) {
    const response = await fetch(url, { signal });
    if (!response.ok) {
        throw new Error(`${url} returned HTTP ${response.status}`);
    }
    return response.json();
}

function loadFavoriteIcon(url, signal) {
    // Rasterize the bundled Heroicons SVG for MapLibre's image API once per map.
    return new Promise(resolve => {
        const image = new Image();
        let timer;
        const finish = value => {
            clearTimeout(timer);
            signal.removeEventListener("abort", cancel);
            image.onload = null;
            image.onerror = null;
            resolve(value);
        };
        const cancel = () => { finish(null); image.src = ""; };
        if (signal.aborted || !url) { finish(null); return; }
        signal.addEventListener("abort", cancel, {once: true});
        timer = setTimeout(cancel, 5000);
        image.onload = () => {
            try {
                const canvas = document.createElement("canvas");
                canvas.width = canvas.height = 48;
                const context = canvas.getContext("2d");
                if (!context) { finish(null); return; }
                context.drawImage(image, 0, 0, 48, 48);
                finish(context.getImageData(0, 0, 48, 48));
            } catch {
                // An unavailable icon must not prevent the country map loading.
                finish(null);
            }
        };
        image.onerror = () => finish(null);
        image.src = url;
    });
}

async function initializeMapPage() {
    const page = document.querySelector('[data-page="map"]');
    if (!page) return;
    if (activeController?.page === page) {
        resumeMapPage(activeController);
        return;
    }
    cleanupMapPage();
    const container = page.querySelector("#world-map");
    container.replaceChildren();
    const abortController = new AbortController();
    const controller = {
        page,
        container,
        abortController,
        map: null,
        suspended: false,
        mapReady: false,
        notesDirty: false,
        feedsDirty: false,
        personalDirty: false,
        countriesByCode: new Map(),
        countryCodes: new Set(),
        preferences: null,
        geometry: null,
        centroids: null,
        capitals: null,
        selectedCode: null,
        hoveredCode: null,
        hoverPoint: null,
        hoverFrame: null,
        layersInstalled: false,
        usingFallbackStyle: false,
        basemapVisibility: new Map(),
        fallbackTimer: null,
        glyphsUrl: page.dataset.mapGlyphsUrl,
        status: page.querySelector("[data-map-status]"),
        notice: page.querySelector("[data-map-notice]"),
        toolbar: page.querySelector(".map-toolbar"),
        controlsToggle: page.querySelector("[data-map-controls-toggle]"),
        controlsPanel: page.querySelector("[data-map-controls-panel]"),
        homeButton: page.querySelector("[data-home-view]"),
        worldButton: page.querySelector("[data-world-view]"),
        homeSummary: page.querySelector("[data-home-summary]"),
        newsContent: page.querySelector("[data-country-news-content]"),
        newsUrlTemplate: page.dataset.countryNewsUrlTemplate,
        newsAbortController: null,
        newsRequestId: 0,
        newsTimer: null,
        pendingNews: null,
        videoContent: page.querySelector("[data-country-videos-content]"),
        videoUrlTemplate: page.dataset.countryVideosUrlTemplate,
        videoAbortController: null,
        videoRequestId: 0,
    };
    activeController = controller;

    document.addEventListener("world-journal:feed-cache-changed", event => {
        const { code, kind, entry } = event.detail;
        if (activeController !== controller || controller.selectedCode !== code) return;
        if (kind === "articles") renderCachedNews(controller, code, entry);
        else if (controller.page.querySelector('[data-country-section="videos"]').getAttribute("aria-selected") === "true") {
            renderCachedVideos(controller, code, entry);
        }
    }, { signal: abortController.signal });

    page.querySelector("[data-country-close]").addEventListener("click", () => closeCountry(controller), { signal: abortController.signal });
    controller.newsContent.addEventListener("click", (event) => {
        if (event.target.closest("[data-news-retry]") && controller.selectedCode) {
            const country = controller.countriesByCode.get(controller.selectedCode);
            loadCountryNews(controller, controller.selectedCode, country.name, { retryFailed: true });
            return;
        }
        const filterButton = event.target.closest("[data-news-filter]");
        if (filterButton) {
            applyNewsFilter(controller, filterButton.dataset.newsFilter);
        }
    }, { signal: abortController.signal });
    page.querySelector("[role='tablist']").addEventListener("click", (event) => {
        const tab = event.target.closest("[data-country-section]");
        if (tab) {
            selectCountrySection(controller, tab.dataset.countrySection);
        }
    }, { signal: abortController.signal });
    page.querySelector("[role='tablist']").addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
            return;
        }
        event.preventDefault();
        const tabs = [...page.querySelectorAll("[data-country-section]")];
        const currentIndex = tabs.indexOf(event.target.closest("[data-country-section]"));
        const nextIndex = event.key === "Home"
            ? 0
            : event.key === "End"
                ? tabs.length - 1
                : (currentIndex + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
        selectCountrySection(controller, tabs[nextIndex].dataset.countrySection, { focus: true });
    }, { signal: abortController.signal });
    controller.videoContent.addEventListener("click", (event) => {
        if (event.target.closest("[data-video-retry]") && controller.selectedCode) {
            const country = controller.countriesByCode.get(controller.selectedCode);
            loadCountryVideos(controller, controller.selectedCode, country.name, { retryFailed: true });
            return;
        }
        const playButton = event.target.closest("[data-video-play]");
        if (playButton) {
            const bookmark = playButton.closest(".country-video-item")?.querySelector("[data-bookmark-url]");
            document.dispatchEvent(new CustomEvent("world-journal:play-video", {
                detail: {
                    videoId: playButton.dataset.videoId,
                    title: playButton.dataset.videoTitle,
                    channel: playButton.dataset.videoChannel,
                    saveUrl: bookmark?.dataset.bookmarkUrl || bookmark?.href,
                },
            }));
        }
    }, { signal: abortController.signal });
    controller.videoContent.addEventListener("error", (event) => {
        if (event.target.matches("[data-video-thumbnail]")) {
            event.target.hidden = true;
        }
    }, { capture: true, signal: abortController.signal });
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || controller.suspended || !controller.page.isConnected) {
            return;
        }
        if (!controller.controlsPanel.hidden) {
            closeControlsPanel(controller, { restoreFocus: true });
        } else if (controller.selectedCode) {
            closeCountry(controller);
        }
    }, { signal: abortController.signal });
    document.addEventListener("world-journal:theme-change", () => updateLayerTheme(controller), { signal: abortController.signal });
    document.addEventListener("world-journal:map-preferences-change", event => {
        if (!controller.mapReady) return;
        controller.preferences = { ...event.detail };
        updateHomeControls(controller);
        if (controller.suspended) updateControls(controller);
        else applyPreferences(controller);
    }, { signal: abortController.signal });
    window.addEventListener("popstate", () => {
        if (activeController !== controller || controller.suspended || location.pathname !== "/") {
            return;
        }
        syncPresetEditor(controller);
        if (controller.presetEditor?.active) return;
        const requested = selectedCodeFromUrl(controller.countriesByCode);
        showNotice(controller, requested.unsupported ? `Country code ${requested.unsupported} is not available in the bundled dataset.` : "");
        renderSelection(controller, requested.code, { fit: Boolean(requested.code) });
        document.dispatchEvent(new CustomEvent("world-journal:location-change"));
    }, { signal: abortController.signal });
    document.addEventListener("world-journal:data-changed", event => {
        const path = event.detail.path;
        if (path.startsWith("/journal/") || path.startsWith("/countries/") || path.startsWith("/settings/backups/")) controller.notesDirty = true;
        if (path.startsWith("/settings/news/") || path.startsWith("/settings/backups/")) controller.feedsDirty = true;
        if (path.startsWith("/countries/") || path.startsWith("/map-presets/") || path.startsWith("/settings/backups/")) controller.personalDirty = true;
    }, {signal: abortController.signal});

    try {
        const [metadata, geometry, capitals, favoriteIcon] = await Promise.all([
            loadJson(page.dataset.countryMetadataUrl, abortController.signal),
            loadJson(page.dataset.countryGeometryUrl, abortController.signal),
            loadJson(page.dataset.capitalGeometryUrl, abortController.signal),
            loadFavoriteIcon(page.dataset.favoriteIconUrl, abortController.signal),
        ]);
        if (activeController !== controller) {
            return;
        }
        if (
            !Array.isArray(metadata.countries)
            || geometry.type !== "FeatureCollection"
            || capitals.type !== "FeatureCollection"
        ) {
            throw new Error("Bundled map data has an invalid schema");
        }
        controller.countriesByCode = new Map(metadata.countries.map((country) => [country.iso_a2, country]));
        controller.countryCodes = new Set(controller.countriesByCode.keys());
        controller.preferences = readMapPreferences(controller.countryCodes);
        controller.geometry = geometry;
        controller.centroids = createCentroids(metadata.countries);
        controller.capitals = capitals;
        controller.favoriteIcon = favoriteIcon;
        initializeCountryFacts(controller);
        initializePersonalMap(controller, selectCountry);
        initializePresetMap(controller, {
            closeCountry: () => closeCountry(controller, {pushHistory: false, focusMap: false}),
            apply: () => applyPersonalLayers(controller),
            refresh: () => loadPersonalData(controller),
            restoreCountry: () => {
                const requested = selectedCodeFromUrl(controller.countriesByCode);
                renderSelection(controller, requested.code, {fit: false});
            },
        });
        initializeControls(controller);
        controller.status.textContent = "Loading map provider…";
        controller.mapReady = true;
        if (!controller.suspended && page.isConnected) createMap(controller, page.dataset.mapStyleUrl);
    } catch (error) {
        if (error.name === "AbortError") {
            return;
        }
        controller.status.textContent = "The bundled country map could not be loaded.";
        controller.status.classList.add("is-error");
        console.error("World Journal map initialization failed", error);
    }
}

function suspendMapPage() {
    const controller = activeController;
    if (!controller || controller.suspended) return;
    controller.suspended = true;
    if (controller.map) {
        clearHover(controller);
        controller.map.stop();
        controller.pausedCamera = {
            center: controller.map.getCenter().toArray(),
            zoom: controller.map.getZoom(),
            bearing: controller.map.getBearing(),
            pitch: controller.map.getPitch(),
            padding: controller.map.getPadding(),
        };
        saveViewport(controller.map);
    }
    // Keep the canvas, loaded layers and drawer nodes. Existing bounded loads
    // may finish into the detached page; its DOM listeners remain installed once.
}

function resumeMapPage(controller) {
    if (!controller.suspended) { syncPresetEditor(controller); return; }
    controller.suspended = false;
    syncPresetEditor(controller);
    if (controller.mapReady) controller.preferences = readMapPreferences(controller.countryCodes);
    if (!controller.map) {
        if (controller.mapReady) createMap(controller, controller.page.dataset.mapStyleUrl);
        return;
    }
    updateHomeControls(controller);
    updateLayerTheme(controller);
    applyPreferences(controller);
    const requested = controller.presetEditor?.active ? {code: null, unsupported: null} : selectedCodeFromUrl(controller.countriesByCode);
    const camera = requested.code === controller.selectedCode ? controller.pausedCamera : null;
    controller.pausedCamera = null;
    showNotice(controller, requested.unsupported ? `Country code ${requested.unsupported} is not available in the bundled dataset.` : "");
    if (requested.code !== controller.selectedCode) {
        renderSelection(controller, requested.code, {fit: Boolean(requested.code)});
    } else {
        const section = new URL(location.href).searchParams.get("section");
        if (["overview", "notes"].includes(section)) selectCountrySection(controller, section);
    }
    if (controller.personalDirty) {
        controller.personalDirty = false;
        loadPersonalData(controller);
    }
    if (controller.notesDirty && controller.personal) {
        controller.notesDirty = false;
        delete controller.personal.notesContent.dataset.loadedCountry;
        if (controller.page.querySelector('[data-country-section="notes"]').getAttribute("aria-selected") === "true") {
            loadCountryNotes(controller, {retry: true});
        }
    }
    if (controller.feedsDirty && controller.selectedCode) {
        controller.feedsDirty = false;
        const country = controller.countriesByCode.get(controller.selectedCode);
        loadCountryNews(controller, country.iso_a2, country.name);
        cancelCountryVideos(controller);
        controller.videoContent.replaceChildren();
        controller.videoContent.setAttribute("aria-busy", "false");
        delete controller.videoContent.dataset.loadedCountry;
        if (controller.page.querySelector('[data-country-section="videos"]').getAttribute("aria-selected") === "true") {
            selectCountrySection(controller, "videos");
        }
    }
    // Resize only after the retained page is visible, including after a device
    // rotation or player layout change while another page was active.
    requestAnimationFrame(() => {
        if (activeController === controller && !controller.suspended) {
            controller.map.resize();
            if (camera && controller.selectedCode === requested.code) controller.map.jumpTo(camera);
        }
    });
}

export function cleanupMapPage() {
    if (!activeController) {
        return;
    }
    const controller = activeController;
    activeController = null;
    cancelHoverFrame(controller);
    window.clearTimeout(controller.fallbackTimer);
    cancelCountryNews(controller, { abort: true });
    cancelCountryVideos(controller);
    controller.abortController.abort();
    controller.attributionObserver?.disconnect();
    if (controller.map) {
        saveViewport(controller.map);
        controller.map.remove();
    }
    controller.container.replaceChildren();
}

export function registerMapPage() {
    if (lifecycleRegistered) {
        return;
    }
    lifecycleRegistered = true;
    document.addEventListener("world-journal:page-ready", (event) => {
        if (event.detail.page === "map") {
            initializeMapPage();
        }
    });
    document.addEventListener("world-journal:page-cleanup", event => {
        if (event.detail?.preserveMap) suspendMapPage();
        else cleanupMapPage();
    });
}
