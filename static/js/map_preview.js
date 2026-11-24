// Start independently of the main app/module graph. Keep only three bounded
// browser-local images; the real map remains responsible for all interaction.
import { WORLD_CAMERA, cameraKey, readViewport } from "./map_camera.js";

const VERSION = 1;
const MAX_IMAGE_BYTES = 1500000;
const MODES = ["terrain", "plain", "adventure"];
const states = new WeakMap();
const sessions = new Set();
let database;
let preferences;
let generation = 0;

function openDatabase() {
    database ??= new Promise(resolve => {
        try {
            const request = indexedDB.open("world-journal-map-preview", VERSION);
            request.onupgradeneeded = () => request.result.createObjectStore("frames", {keyPath: "mode"});
            request.onsuccess = () => {
                const db = request.result;
                db.onversionchange = () => { db.close(); database = null; };
                resolve(db);
            };
            request.onerror = request.onblocked = () => resolve(null);
        } catch { resolve(null); }
    });
    return database;
}

async function readFrame(mode) {
    try {
        const db = await openDatabase();
        if (!db) return null;
        return await new Promise(resolve => {
            const request = db.transaction("frames").objectStore("frames").get(mode);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => resolve(null);
        });
    } catch { return null; }
}

async function writeFrame(frame, epoch) {
    try {
        const db = await openDatabase();
        if (!db || epoch !== generation) return;
        const transaction = db.transaction("frames", "readwrite");
        transaction.objectStore("frames").put(frame);
        await new Promise(resolve => { transaction.oncomplete = transaction.onerror = transaction.onabort = resolve; });
    } catch {
        // Private browsing, quotas and denied storage affect only the preview.
    }
}

function snapshot() {
    preferences ??= JSON.parse(document.querySelector("#app-preferences")?.textContent || "null");
    return preferences;
}

function context(page) {
    const prefs = snapshot();
    const params = new URL(location.href).searchParams;
    if (!prefs || !MODES.includes(prefs.mapType) || ["country", "place", "edit_preset"].some(key => params.has(key))) return null;
    const signature = JSON.stringify([VERSION,
        Object.keys(prefs).filter(key => key !== "revision").sort().map(key => [key, prefs[key]]),
        page.dataset.mapStyleUrl, page.dataset.countryGeometryUrl, page.dataset.capitalGeometryUrl, page.dataset.adventureDataUrl,
        ...(prefs.mapType === "adventure" ? ["water-only-artwork"] : [])]);
    const intent = prefs.homeCountry ? `home:${prefs.homeCountry}` : cameraKey(readViewport() ?? WORLD_CAMERA);
    const workspace = page.querySelector(".map-workspace");
    return {mode: prefs.mapType, signature, intent, width: workspace.clientWidth, height: workspace.clientHeight};
}

function stateFor(page) {
    if (!states.has(page)) states.set(page, {page, image: page.querySelector("[data-map-preview-image]"), ready: false, token: 0, url: null});
    return states.get(page);
}

function hide(state) {
    state.token++;
    if (state.image) {
        state.image.hidden = true;
        state.image.removeAttribute("src");
    }
    if (state.url) URL.revokeObjectURL(state.url);
    state.url = null;
}

async function show(page) {
    if (!page) return;
    const state = stateFor(page);
    if (state.ready || !state.image || !page.isConnected) return;
    const wanted = context(page);
    if (!wanted) { hide(state); return; }
    const requestKey = JSON.stringify(wanted);
    if (state.requestKey === requestKey) return;
    hide(state);
    state.requestKey = requestKey;
    page.dataset.mapType = wanted.mode;
    const token = ++state.token, epoch = generation;
    const frame = await readFrame(wanted.mode);
    if (!frame || token !== state.token || epoch !== generation || state.ready || !page.isConnected
        || frame.signature !== wanted.signature || frame.intent !== wanted.intent
        || Math.abs(frame.width - wanted.width) > 1 || Math.abs(frame.height - wanted.height) > 1
        || !(frame.blob instanceof Blob) || frame.blob.size > MAX_IMAGE_BYTES) return;
    const url = URL.createObjectURL(frame.blob);
    state.image.src = url;
    try { await state.image.decode(); } catch { URL.revokeObjectURL(url); return; }
    if (token !== state.token || epoch !== generation || state.ready || !page.isConnected) { URL.revokeObjectURL(url); return; }
    if (state.url) URL.revokeObjectURL(state.url);
    state.url = url;
    state.image.hidden = false;
    page.dataset.mapPreview = "shown";
}

function camera(map) {
    return {center: map.getCenter().toArray(), zoom: map.getZoom()};
}

function paddingKey(map) {
    const padding = map.getPadding();
    return JSON.stringify([padding.top, padding.right, padding.bottom, padding.left]);
}

export function connectMapPreview(controller) {
    const {page, map} = controller;
    const state = stateFor(page);
    let disposed = false, pending = false, lastAttempt = null, homeRequested = false;
    let home = controller.preferences.homeCountry && !controller.selectedCode
        ? {code: controller.preferences.homeCountry, key: cameraKey(camera(map)), padding: paddingKey(map),
            width: controller.container.clientWidth, height: controller.container.clientHeight} : null;

    const eligible = () => !disposed && page.isConnected && !controller.suspended && !document.hidden
        && controller.layersInstalled && !controller.usingFallbackStyle && !map.isMoving()
        && !controller.selectedCode && !controller.hoveredCode && !controller.presetEditor?.active
        && Boolean(controller.personal?.ready);

    function capture() {
        if (!eligible() || pending) return;
        const wanted = context(page);
        if (!wanted || Math.abs(map.getBearing()) > .001 || Math.abs(map.getPitch()) > .001) return;
        const position = camera(map), positionKey = cameraKey(position);
        if (homeRequested) {
            home = {code: controller.preferences.homeCountry, key: positionKey, padding: paddingKey(map), width: wanted.width, height: wanted.height};
            homeRequested = false;
        }
        if (controller.preferences.homeCountry) {
            if (home?.code !== controller.preferences.homeCountry || home.key !== positionKey || home.padding !== paddingKey(map)
                || home.width !== wanted.width || home.height !== wanted.height) return;
        } else if (Object.values(map.getPadding()).some(value => value !== 0)) return;
        const key = JSON.stringify([wanted, positionKey, generation, controller.styleGeneration,
            controller.basemapLayers.some(layer => layer["source-layer"] === "place")]);
        if (key === lastAttempt) return;
        lastAttempt = key;
        pending = true;
        const epoch = generation;
        // Read the WebGL canvas during render, before its back buffer is cleared.
        // This avoids preserveDrawingBuffer's permanent rendering overhead.
        const onRender = () => {
            pending = false;
            if (!eligible() || epoch !== generation || positionKey !== cameraKey(camera(map))) { lastAttempt = null; return; }
            try {
                const source = map.getCanvas();
                const scale = Math.min(1, 2560 / source.width, Math.sqrt(3000000 / (source.width * source.height)));
                if (!Number.isFinite(scale) || scale <= 0) return;
                const canvas = document.createElement("canvas");
                canvas.width = Math.max(1, Math.round(source.width * scale));
                canvas.height = Math.max(1, Math.round(source.height * scale));
                canvas.getContext("2d").drawImage(source, 0, 0, canvas.width, canvas.height);
                canvas.toBlob(blob => {
                    if (!blob || blob.size > MAX_IMAGE_BYTES || disposed || epoch !== generation
                        || wanted.signature !== context(page)?.signature || positionKey !== cameraKey(camera(map))) return;
                    void writeFrame({...wanted, camera: position, blob}, epoch);
                }, "image/webp", .85);
            } catch { /* A preview failure never interrupts the map. */ }
        };
        state.onRender = onRender;
        map.once("render", onRender);
        map.triggerRepaint();
    }

    function idle() {
        if (disposed || controller.suspended || !page.isConnected || !controller.layersInstalled) return;
        state.ready = true;
        hide(state);
        page.dataset.mapPreview = "live";
        capture();
    }

    const moving = () => hide(state);
    const session = {invalidate() { lastAttempt = null; hide(state); if (state.ready && eligible()) map.triggerRepaint(); }};
    sessions.add(session);
    map.on("idle", idle);
    map.on("movestart", moving);
    return {
        home() { homeRequested = true; },
        invalidate,
        disconnect() {
            disposed = true;
            map.off("idle", idle);
            map.off("movestart", moving);
            if (state.onRender) map.off("render", state.onRender);
            sessions.delete(session);
            hide(state);
        },
    };
}

async function invalidate() {
    generation++;
    for (const session of sessions) session.invalidate();
    try {
        const db = await openDatabase();
        db?.transaction("frames", "readwrite").objectStore("frames").clear();
    } catch { /* Storage is optional. */ }
}

document.addEventListener("world-journal:app-preferences-change", event => {
    preferences = event.detail;
    const page = document.querySelector("[data-page='map']");
    if (page && !states.get(page)?.ready) void show(page);
});
document.addEventListener("world-journal:data-changed", event => {
    if (/^\/(countries|map-presets|settings\/backups)\//.test(event.detail?.path || "")) void invalidate();
});
document.addEventListener("world-journal:country-metadata-changed", () => { void invalidate(); });
document.addEventListener("world-journal:page-ready", event => {
    if (event.detail.page === "map") void show(document.querySelector("[data-page='map']"));
});
const firstPage = document.querySelector("[data-page='map']");
if (firstPage) void show(firstPage);
