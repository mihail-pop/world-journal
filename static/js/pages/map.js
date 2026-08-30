import {
    AttributionControl,
    Map as MapLibreMap,
    NavigationControl,
} from "../../vendor/maplibre-gl/maplibre-gl.mjs";

const VIEWPORT_STORAGE_KEY = "world-journal:map-viewport";
const WORLD_CAMERA = { center: [8, 18], zoom: 1.35 };
const SOURCE_ID = "world-journal-countries";
const CENTROID_SOURCE_ID = "world-journal-country-centroids";
const LAYERS = {
    fill: "world-journal-country-fill",
    outline: "world-journal-country-outline",
    hoverFill: "world-journal-country-hover-fill",
    hoverLine: "world-journal-country-hover-line",
    selectedFill: "world-journal-country-selected-fill",
    selectedLine: "world-journal-country-selected-line",
    smallMarker: "world-journal-country-small-marker",
    hitTarget: "world-journal-country-hit-target",
};
const FALLBACK_STYLE = {
    version: 8,
    sources: {},
    layers: [{ id: "world-journal-background", type: "background", paint: { "background-color": "#0b1622" } }],
};

let lifecycleRegistered = false;
let activeController = null;

function readViewport() {
    try {
        const value = JSON.parse(localStorage.getItem(VIEWPORT_STORAGE_KEY));
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
        localStorage.setItem(VIEWPORT_STORAGE_KEY, JSON.stringify({
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

    map.setPaintProperty(LAYERS.fill, "fill-color", countryFill);
    map.setPaintProperty(LAYERS.outline, "line-color", countryOutline);
    map.setPaintProperty(LAYERS.hoverFill, "fill-color", hover);
    map.setPaintProperty(LAYERS.hoverLine, "line-color", hover);
    map.setPaintProperty(LAYERS.selectedFill, "fill-color", hover);
    map.setPaintProperty(LAYERS.selectedLine, "line-color", selected);
    map.setPaintProperty(LAYERS.smallMarker, "circle-color", hover);
    map.setPaintProperty(LAYERS.smallMarker, "circle-stroke-color", selected);
    if (controller.usingFallbackStyle) {
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

function drawerPadding(country) {
    if (window.matchMedia("(max-width: 46rem)").matches) {
        return { top: 56, right: 36, bottom: 260, left: 36 };
    }
    return { top: 56, right: 380, bottom: 56, left: 56 };
}

function focusCountry(controller, country, animate = true) {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    controller.map.fitBounds(country.bounds, {
        padding: drawerPadding(country),
        maxZoom: country.small ? 7 : 5.5,
        duration: animate && !reducedMotion ? 650 : 0,
    });
}

function renderSelection(controller, code, { fit = true, focusDrawer = false } = {}) {
    controller.selectedCode = code;
    updateFilter(controller.map, LAYERS.selectedFill, code);
    updateFilter(controller.map, LAYERS.selectedLine, code);
    const drawer = controller.page.querySelector("[data-country-drawer]");

    if (!code) {
        drawer.hidden = true;
        controller.page.classList.remove("has-country-drawer");
        return;
    }

    const country = controller.countriesByCode.get(code);
    controller.page.querySelector("[data-country-flag]").textContent = country.flag;
    controller.page.querySelector("[data-country-name]").textContent = country.name;
    controller.page.querySelector("[data-country-code]").textContent = `${country.iso_a2} · ${country.iso_a3}`;
    controller.page.querySelector("[data-country-region]").textContent = country.region;
    controller.page.querySelector("[data-country-subregion]").textContent = country.subregion;
    drawer.hidden = false;
    controller.page.classList.add("has-country-drawer");
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

function installCountryLayers(controller) {
    const { map } = controller;
    if (map.getSource(SOURCE_ID)) {
        return;
    }
    map.addSource(SOURCE_ID, { type: "geojson", data: controller.geometry, promoteId: "iso_a2" });
    map.addSource(CENTROID_SOURCE_ID, { type: "geojson", data: controller.centroids });
    map.addLayer({ id: LAYERS.fill, type: "fill", source: SOURCE_ID, paint: { "fill-color": "#32445b", "fill-opacity": 0.22 } });
    map.addLayer({ id: LAYERS.outline, type: "line", source: SOURCE_ID, paint: { "line-color": "#8596a5", "line-opacity": 0.62, "line-width": 0.8 } });
    map.addLayer({ id: LAYERS.hoverFill, type: "fill", source: SOURCE_ID, filter: ["==", ["get", "iso_a2"], ""], paint: { "fill-color": "#00bfff", "fill-opacity": 0.32 } });
    map.addLayer({ id: LAYERS.hoverLine, type: "line", source: SOURCE_ID, filter: ["==", ["get", "iso_a2"], ""], paint: { "line-color": "#00bfff", "line-width": 2 } });
    map.addLayer({ id: LAYERS.selectedFill, type: "fill", source: SOURCE_ID, filter: ["==", ["get", "iso_a2"], ""], paint: { "fill-color": "#00bfff", "fill-opacity": 0.26 } });
    map.addLayer({ id: LAYERS.selectedLine, type: "line", source: SOURCE_ID, filter: ["==", ["get", "iso_a2"], ""], paint: { "line-color": "#a8b5c4", "line-width": 3.5 } });
    map.addLayer({
        id: LAYERS.smallMarker,
        type: "circle",
        source: CENTROID_SOURCE_ID,
        filter: ["==", ["get", "small"], true],
        paint: { "circle-color": "#00bfff", "circle-radius": 3.5, "circle-stroke-color": "#a8b5c4", "circle-stroke-width": 1.5 },
    });
    map.addLayer({
        id: LAYERS.hitTarget,
        type: "circle",
        source: CENTROID_SOURCE_ID,
        paint: { "circle-color": "#00bfff", "circle-radius": 11, "circle-opacity": 0.01 },
    });
    controller.layersInstalled = true;
    updateLayerTheme(controller);
    updateFilter(map, LAYERS.selectedFill, controller.selectedCode);
    updateFilter(map, LAYERS.selectedLine, controller.selectedCode);
    controller.status.hidden = true;
    if (controller.selectedCode) {
        focusCountry(controller, controller.countriesByCode.get(controller.selectedCode), false);
    }
}

function createCentroids(countries) {
    return {
        type: "FeatureCollection",
        features: countries.map((country) => ({
            type: "Feature",
            id: country.iso_a2,
            properties: { iso_a2: country.iso_a2, small: country.small },
            geometry: { type: "Point", coordinates: country.centroid },
        })),
    };
}

function initialCamera(selectedCountry) {
    if (selectedCountry) {
        return { center: selectedCountry.centroid, zoom: selectedCountry.small ? 6 : 3.2 };
    }
    return readViewport() ?? WORLD_CAMERA;
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
    controller.status.textContent = "Map provider unavailable. Showing bundled country boundaries.";
    controller.map.setStyle(FALLBACK_STYLE);
}

function createMap(controller, styleUrl) {
    const requested = selectedCodeFromUrl(controller.countriesByCode);
    controller.selectedCode = requested.code;
    if (requested.unsupported) {
        showNotice(controller, `Country code ${requested.unsupported} is not available in the bundled dataset.`);
    }
    const camera = initialCamera(requested.code ? controller.countriesByCode.get(requested.code) : null);
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
        customAttribution: [
            '<a href="https://openfreemap.org/" target="_blank" rel="noopener noreferrer">OpenFreeMap</a>',
            '<a href="https://www.naturalearthdata.com/" target="_blank" rel="noopener noreferrer">Country boundaries: Natural Earth</a>',
        ],
    }), "bottom-left");

    controller.fallbackTimer = window.setTimeout(() => applyProviderFallback(controller), 8000);
    map.on("style.load", () => {
        window.clearTimeout(controller.fallbackTimer);
        installCountryLayers(controller);
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
        geometry: null,
        centroids: null,
        selectedCode: null,
        hoveredCode: null,
        layersInstalled: false,
        usingFallbackStyle: false,
        fallbackTimer: null,
        status: page.querySelector("[data-map-status]"),
        notice: page.querySelector("[data-map-notice]"),
    };
    activeController = controller;

    page.querySelector("[data-country-close]").addEventListener("click", () => closeCountry(controller), { signal: abortController.signal });
    page.querySelector("[data-world-view]").addEventListener("click", () => {
        closeCountry(controller, { focusMap: false });
        try {
            localStorage.removeItem(VIEWPORT_STORAGE_KEY);
        } catch (error) {
            // Reset still updates the active map when storage is unavailable.
        }
        const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        controller.map?.easeTo({ ...WORLD_CAMERA, duration: reducedMotion ? 0 : 650 });
    }, { signal: abortController.signal });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && controller.selectedCode) {
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
        const [metadata, geometry] = await Promise.all([
            loadJson(page.dataset.countryMetadataUrl, abortController.signal),
            loadJson(page.dataset.countryGeometryUrl, abortController.signal),
        ]);
        if (activeController !== controller) {
            return;
        }
        if (!Array.isArray(metadata.countries) || geometry.type !== "FeatureCollection") {
            throw new Error("Bundled country data has an invalid schema");
        }
        controller.countriesByCode = new Map(metadata.countries.map((country) => [country.iso_a2, country]));
        controller.geometry = geometry;
        controller.centroids = createCentroids(metadata.countries);
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