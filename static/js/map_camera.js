export const WORLD_CAMERA = Object.freeze({center: [8, 18], zoom: 1.35});
export const MAP_VIEWPORT_STORAGE_KEY = "world-journal:map-viewport";

export function readViewport() {
    try {
        const value = JSON.parse(localStorage.getItem(MAP_VIEWPORT_STORAGE_KEY));
        if (Array.isArray(value?.center) && value.center.length === 2
            && value.center.every(Number.isFinite) && Number.isFinite(value.zoom)) return value;
    } catch {
        // A denied browser cache must not prevent the live map from opening.
    }
    return null;
}

export function saveViewport(map) {
    try {
        localStorage.setItem(MAP_VIEWPORT_STORAGE_KEY, JSON.stringify({
            center: map.getCenter().toArray(), zoom: map.getZoom(),
        }));
    } catch {
        // Only the camera is browser-local; Preferences live in AppSettings.
    }
}

export function cameraKey(camera) {
    return JSON.stringify([...camera.center.map(value => Math.round(value * 100000) / 100000),
        Math.round(camera.zoom * 10000) / 10000]);
}
