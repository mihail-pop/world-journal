import {
    AttributionControl,
    Map as MapLibreMap,
    NavigationControl,
} from "../../vendor/maplibre-gl/maplibre-gl.mjs";
import {
    clearSavedMapViewport,
    MAP_VIEWPORT_STORAGE_KEY,
    readMapPreferences,
    writeMapPreferences,
} from "../map_preferences.js";

const WORLD_CAMERA = { center: [8, 18], zoom: 1.35 };
const SOURCE_ID = "world-journal-countries";
const CENTROID_SOURCE_ID = "world-journal-country-centroids";
const CAPITAL_SOURCE_ID = "world-journal-capitals";
const LAYERS = {
    simpleBackground: "world-journal-simple-background",
    fill: "world-journal-country-fill",
    outline: "world-journal-country-outline",
    hoverFill: "world-journal-country-hover-fill",
    hoverLine: "world-journal-country-hover-line",
    selectedFill: "world-journal-country-selected-fill",
    selectedLine: "world-journal-country-selected-line",
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
    map.setPaintProperty(LAYERS.simpleBackground, "background-color", getThemeColor("--bg-tertiary"));
    map.setPaintProperty(LAYERS.fill, "fill-color", countryFill);
    map.setPaintProperty(LAYERS.outline, "line-color", countryOutline);
    map.setPaintProperty(LAYERS.hoverFill, "fill-color", hover);
    map.setPaintProperty(LAYERS.hoverLine, "line-color", hover);
    map.setPaintProperty(LAYERS.selectedFill, "fill-color", hover);
    map.setPaintProperty(LAYERS.selectedLine, "line-color", selected);
    map.setPaintProperty(LAYERS.smallMarker, "circle-color", hover);
    map.setPaintProperty(LAYERS.smallMarker, "circle-stroke-color", selected);
    map.setPaintProperty(LAYERS.countryNames, "text-color", selected);
    map.setPaintProperty(LAYERS.countryNames, "text-halo-color", background);
    map.setPaintProperty(LAYERS.capitalMarkers, "circle-color", selected);
    map.setPaintProperty(LAYERS.capitalMarkers, "circle-stroke-color", background);
    map.setPaintProperty(LAYERS.capitalNames, "text-color", selected);
    map.setPaintProperty(LAYERS.capitalNames, "text-halo-color", background);
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
    if (code) {
        url.searchParams.set("country", code);
    } else {
        url.searchParams.delete("country");
    }
    history.pushState({ worldJournalCountry: code }, "", url);
}

function updateFilter(map, layerId, code) {
    if (map.getLayer(layerId)) {
        map.setFilter(layerId, ["==", ["get", "iso_a2"], code ?? ""]);
    }
}

function drawerPadding() {
    if (window.matchMedia("(max-width: 46rem)").matches) {
        return { top: 56, right: 36, bottom: 260, left: 36 };
    }
    return { top: 56, right: 380, bottom: 56, left: 56 };
}

function focusCountry(controller, country, animate = true) {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    controller.map.fitBounds(country.bounds, {
        padding: drawerPadding(),
        maxZoom: country.small ? 7 : 5.5,
        duration: animate && !reducedMotion ? 650 : 0,
    });
}

function cancelCountryNews(controller) {
    controller.newsRequestId += 1;
    controller.newsAbortController?.abort();
    controller.newsAbortController = null;
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

async function loadCountryNews(controller, code, countryName, { retryFailed = false } = {}) {
    cancelCountryNews(controller);
    const requestId = controller.newsRequestId;
    const abortController = new AbortController();
    controller.newsAbortController = abortController;
    controller.newsContent.setAttribute("aria-busy", "true");
    showNewsMessage(controller, `Loading current English-language headlines for ${countryName}…`);
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
        controller.newsContent.innerHTML = markup;
        controller.newsContent.setAttribute("aria-busy", "false");
        applyNewsFilter(controller, "all");
    } catch (error) {
        if (error.name === "AbortError" || activeController !== controller || controller.newsRequestId !== requestId) {
            return;
        }
        controller.newsContent.setAttribute("aria-busy", "false");
        showNewsMessage(controller, "Current news could not be loaded.", { retry: true });
        console.error("World Journal country news request failed", error);
    } finally {
        if (controller.newsRequestId === requestId) {
            controller.newsAbortController = null;
        }
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
    const requestId = controller.videoRequestId;
    const abortController = new AbortController();
    controller.videoAbortController = abortController;
    controller.videoContent.setAttribute("aria-busy", "true");
    showVideoMessage(controller, `Loading recent videos for ${countryName}…`);
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
        controller.videoContent.innerHTML = markup;
        controller.videoContent.dataset.loadedCountry = code;
        controller.videoContent.setAttribute("aria-busy", "false");
    } catch (error) {
        if (error.name === "AbortError" || activeController !== controller || controller.videoRequestId !== requestId) {
            return;
        }
        controller.videoContent.setAttribute("aria-busy", "false");
        showVideoMessage(controller, "Current videos could not be loaded.", { retry: true });
        console.error("World Journal country videos request failed", error);
    } finally {
        if (controller.videoRequestId === requestId) {
            controller.videoAbortController = null;
        }
    }
}

function selectCountrySection(controller, section, { focus = false } = {}) {
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
    controller.selectedCode = code;
    updateFilter(controller.map, LAYERS.selectedFill, code);
    updateFilter(controller.map, LAYERS.selectedLine, code);
    const drawer = controller.page.querySelector("[data-country-drawer]");

    if (!code) {
        cancelCountryNews(controller);
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
    controller.page.querySelector("[data-country-region]").textContent = country.region;
    controller.page.querySelector("[data-country-subregion]").textContent = country.subregion;
    drawer.hidden = false;
    controller.page.classList.add("has-country-drawer");
    loadCountryNews(controller, code, country.name);
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
    if (options.pushHistory !== false && code !== controller.selectedCode) {
        updateHistory(code);
    }
    renderSelection(controller, code, options);
}

function closeCountry(controller, { pushHistory = true, focusMap = true } = {}) {
    if (pushHistory && (controller.selectedCode || new URL(window.location.href).searchParams.has("country"))) {
        updateHistory(null);
    }
    renderSelection(controller, null, { fit: false });
    if (focusMap) {
        controller.container.focus({ preventScroll: true });
    }
}

function queryCountryCode(controller, point) {
    const layers = [LAYERS.hitTarget, LAYERS.fill].filter((layerId) => controller.map.getLayer(layerId));
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
    for (const layer of controller.map.getStyle().layers ?? []) {
        if (isApplicationLayer(layer)) {
            continue;
        }
        const visibility = originalVisibility(controller, layer);
        const hidden = !controller.preferences.terrain
            || isBasemapCountryLabel(layer)
            || isBasemapCapitalLabel(layer)
            || (!controller.preferences.allOtherText && layer.type === "symbol");
        controller.map.setLayoutProperty(
            layer.id,
            "visibility",
            hidden ? "none" : visibility,
        );
    }
}

function setLayerVisibility(map, layerId, visible) {
    if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
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
    controller.map.setPaintProperty(
        LAYERS.fill,
        "fill-opacity",
        controller.preferences.terrain ? 0.22 : 0.72,
    );
    updateLayerTheme(controller);
    const styleLayers = controller.map.getStyle().layers ?? [];
    const isVisible = (layerId) => controller.map.getLayoutProperty(layerId, "visibility") !== "none";
    const basemapCountryLabels = styleLayers.filter((layer) => (
        !isApplicationLayer(layer) && isBasemapCountryLabel(layer)
    ));
    const basemapCapitalLabels = styleLayers.filter((layer) => (
        !isApplicationLayer(layer) && isBasemapCapitalLabel(layer)
    ));
    const visibleBasemapLayers = styleLayers.filter((layer) => (
        !isApplicationLayer(layer) && isVisible(layer.id)
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
        styleLayers.filter(isApplicationLayer).length,
    );
}

function addLayer(controller, definition, beforeId) {
    if (!controller.map.getLayer(definition.id)) {
        controller.map.addLayer(definition, beforeId);
    }
}

function installCountryLayers(controller) {
    const { map } = controller;
    const firstBasemapLayer = map.getStyle().layers?.find((layer) => !isApplicationLayer(layer))?.id;
    if (!map.getSource(SOURCE_ID)) {
        map.addSource(SOURCE_ID, { type: "geojson", data: controller.geometry, promoteId: "iso_a2" });
    }
    if (!map.getSource(CENTROID_SOURCE_ID)) {
        map.addSource(CENTROID_SOURCE_ID, { type: "geojson", data: controller.centroids });
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
    addLayer(controller, { id: LAYERS.fill, type: "fill", source: SOURCE_ID, paint: { "fill-color": "#32445b", "fill-opacity": 0.22 } });
    addLayer(controller, { id: LAYERS.outline, type: "line", source: SOURCE_ID, paint: { "line-color": "#8596a5", "line-opacity": 0.62, "line-width": 0.8 } });
    addLayer(controller, { id: LAYERS.hoverFill, type: "fill", source: SOURCE_ID, filter: ["==", ["get", "iso_a2"], ""], paint: { "fill-color": "#00bfff", "fill-opacity": 0.32 } });
    addLayer(controller, { id: LAYERS.hoverLine, type: "line", source: SOURCE_ID, filter: ["==", ["get", "iso_a2"], ""], paint: { "line-color": "#00bfff", "line-width": 2 } });
    addLayer(controller, { id: LAYERS.selectedFill, type: "fill", source: SOURCE_ID, filter: ["==", ["get", "iso_a2"], ""], paint: { "fill-color": "#00bfff", "fill-opacity": 0.26 } });
    addLayer(controller, { id: LAYERS.selectedLine, type: "line", source: SOURCE_ID, filter: ["==", ["get", "iso_a2"], ""], paint: { "line-color": "#a8b5c4", "line-width": 3.5 } });
    addLayer(controller, {
        id: LAYERS.smallMarker,
        type: "circle",
        source: CENTROID_SOURCE_ID,
        filter: ["==", ["get", "small"], true],
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
    applyPreferences(controller);
    updateFilter(map, LAYERS.selectedFill, controller.selectedCode);
    updateFilter(map, LAYERS.selectedLine, controller.selectedCode);
    controller.status.hidden = true;
    if (controller.initialFocusCode) {
        focusCountry(controller, controller.countriesByCode.get(controller.initialFocusCode), false);
        controller.initialFocusCode = null;
    }
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
    const requested = selectedCodeFromUrl(controller.countriesByCode);
    controller.selectedCode = requested.code;
    if (requested.unsupported) {
        showNotice(controller, `Country code ${requested.unsupported} is not available in the bundled dataset.`);
    }
    const selectedCountry = requested.code ? controller.countriesByCode.get(requested.code) : null;
    const homeCountry = controller.preferences.homeCountry
        ? controller.countriesByCode.get(controller.preferences.homeCountry)
        : null;
    const savedViewport = readViewport();
    controller.initialFocusCode = requested.code ?? controller.preferences.homeCountry;
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
    };
    collapseAttribution();
    map.on("resize", collapseAttribution);
    map.on("idle", collapseAttribution);

    controller.fallbackTimer = window.setTimeout(() => applyProviderFallback(controller), 8000);
    map.on("style.load", () => {
        window.clearTimeout(controller.fallbackTimer);
        controller.layersInstalled = false;
        controller.basemapVisibility.clear();
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
    map.on("moveend", () => saveViewport(map));
    map.on("mousemove", (event) => {
        const code = queryCountryCode(controller, event.point);
        if (code === controller.hoveredCode) {
            return;
        }
        controller.hoveredCode = code;
        updateFilter(map, LAYERS.hoverFill, code);
        updateFilter(map, LAYERS.hoverLine, code);
        map.getCanvas().style.cursor = code ? "pointer" : "";
    });
    map.on("click", (event) => {
        const code = queryCountryCode(controller, event.point);
        if (code) {
            selectCountry(controller, code, { fit: true, focusDrawer: true });
        }
    });
    map.getCanvas().addEventListener("mouseleave", () => {
        controller.hoveredCode = null;
        updateFilter(map, LAYERS.hoverFill, null);
        updateFilter(map, LAYERS.hoverLine, null);
        map.getCanvas().style.cursor = "";
    }, { signal: controller.abortController.signal });
    if (requested.code) {
        renderSelection(controller, requested.code, { fit: false });
    }
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

function initializeControls(controller) {
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
        controller.preferences = writeMapPreferences(
            { ...controller.preferences, [key]: input.checked },
            controller.countryCodes,
        );
        applyPreferences(controller);
    }, { signal: controller.abortController.signal });
    controller.homeButton.addEventListener("click", () => {
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
        controller.map?.easeTo({ ...WORLD_CAMERA, duration: reducedMotion ? 0 : 650 });
    }, { signal: controller.abortController.signal });
    document.addEventListener("pointerdown", (event) => {
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

async function initializeMapPage() {
    const page = document.querySelector('[data-page="map"]');
    if (!page || activeController?.page === page) {
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
        countriesByCode: new Map(),
        countryCodes: new Set(),
        preferences: null,
        geometry: null,
        centroids: null,
        capitals: null,
        selectedCode: null,
        hoveredCode: null,
        layersInstalled: false,
        usingFallbackStyle: false,
        basemapVisibility: new Map(),
        fallbackTimer: null,
        initialFocusCode: null,
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
        videoContent: page.querySelector("[data-country-videos-content]"),
        videoUrlTemplate: page.dataset.countryVideosUrlTemplate,
        videoAbortController: null,
        videoRequestId: 0,
    };
    activeController = controller;

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
            document.dispatchEvent(new CustomEvent("world-journal:play-video", {
                detail: {
                    videoId: playButton.dataset.videoId,
                    title: playButton.dataset.videoTitle,
                    channel: playButton.dataset.videoChannel,
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
        if (event.key !== "Escape") {
            return;
        }
        if (!controller.controlsPanel.hidden) {
            closeControlsPanel(controller, { restoreFocus: true });
        } else if (controller.selectedCode) {
            closeCountry(controller);
        }
    }, { signal: abortController.signal });
    document.addEventListener("world-journal:theme-change", () => updateLayerTheme(controller), { signal: abortController.signal });
    window.addEventListener("popstate", () => {
        if (activeController !== controller) {
            return;
        }
        const requested = selectedCodeFromUrl(controller.countriesByCode);
        showNotice(controller, requested.unsupported ? `Country code ${requested.unsupported} is not available in the bundled dataset.` : "");
        renderSelection(controller, requested.code, { fit: Boolean(requested.code) });
    }, { signal: abortController.signal });

    try {
        const [metadata, geometry, capitals] = await Promise.all([
            loadJson(page.dataset.countryMetadataUrl, abortController.signal),
            loadJson(page.dataset.countryGeometryUrl, abortController.signal),
            loadJson(page.dataset.capitalGeometryUrl, abortController.signal),
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
        initializeControls(controller);
        controller.status.textContent = "Loading map provider…";
        createMap(controller, page.dataset.mapStyleUrl);
    } catch (error) {
        if (error.name === "AbortError") {
            return;
        }
        controller.status.textContent = "The bundled country map could not be loaded.";
        controller.status.classList.add("is-error");
        console.error("World Journal map initialization failed", error);
    }
}

export function cleanupMapPage() {
    if (!activeController) {
        return;
    }
    const controller = activeController;
    activeController = null;
    window.clearTimeout(controller.fallbackTimer);
    cancelCountryNews(controller);
    cancelCountryVideos(controller);
    controller.abortController.abort();
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
    document.addEventListener("world-journal:page-cleanup", cleanupMapPage);
}