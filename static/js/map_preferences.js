import { readAppPreferences, writeAppPreferences } from "./app_preferences.js";
import { MAP_VIEWPORT_STORAGE_KEY } from "./map_camera.js";

export { MAP_VIEWPORT_STORAGE_KEY };

export const FAVORITES_DISPLAY_MODES = Object.freeze(["hearts", "list", "none"]);

export const DEFAULT_MAP_PREFERENCES = Object.freeze({
    homeCountry: null, countryNames: true, capitalNames: false, cityNames: true,
    regionNames: false, smallCountryMarkers: false, terrain: true, mapType: "terrain",
    allOtherText: true, protectedAreas: false, vegetation: true, relief: true,
    water: true, transport: true, buildings: false, landUse: false,
    administrativeBorders: true, pointsOfInterest: false,
    favoritesDisplay: "hearts", mapMenuPosition: null, mapMenuOpen: false,
});

export const MAP_BOOLEAN_PREFERENCES = Object.freeze([
    "countryNames", "capitalNames", "cityNames", "regionNames", "smallCountryMarkers",
    "allOtherText", "protectedAreas", "vegetation", "relief", "water", "transport",
    "buildings", "landUse", "administrativeBorders", "pointsOfInterest",
]);

function normalized(value, validCountryCodes) {
    const result = {...DEFAULT_MAP_PREFERENCES};
    for (const key of MAP_BOOLEAN_PREFERENCES) {
        if (typeof value[key] === "boolean") result[key] = value[key];
    }
    if (["terrain", "plain", "adventure"].includes(value.mapType)) result.mapType = value.mapType;
    if (FAVORITES_DISPLAY_MODES.includes(value.favoritesDisplay)) result.favoritesDisplay = value.favoritesDisplay;
    if (typeof value.mapMenuOpen === "boolean") result.mapMenuOpen = value.mapMenuOpen;
    const position = value.mapMenuPosition;
    if (position && [position.x, position.y].every(coordinate => Number.isFinite(coordinate) && coordinate >= 0 && coordinate <= 1)) result.mapMenuPosition = {x: position.x, y: position.y};
    result.terrain = result.mapType === "terrain";
    if (typeof value.homeCountry === "string" && (!validCountryCodes || validCountryCodes.has(value.homeCountry))) result.homeCountry = value.homeCountry;
    return result;
}

export function readMapPreferences(validCountryCodes) {
    return normalized(readAppPreferences(), validCountryCodes);
}

export function writeMapPreferences(value, validCountryCodes, options = {}) {
    const current = readMapPreferences(validCountryCodes);
    const next = normalized(value, validCountryCodes);
    const patch = {};
    for (const key of [...MAP_BOOLEAN_PREFERENCES, "mapType", "homeCountry", "favoritesDisplay", "mapMenuOpen"]) {
        if (next[key] !== current[key]) patch[key] = next[key];
    }
    if (JSON.stringify(next.mapMenuPosition) !== JSON.stringify(current.mapMenuPosition)) patch.mapMenuPosition = next.mapMenuPosition;
    writeAppPreferences(patch, options);
    return readMapPreferences(validCountryCodes);
}

let previous = "";
document.addEventListener("world-journal:app-preferences-change", () => {
    const values = readMapPreferences();
    const signature = JSON.stringify(values);
    if (signature === previous) return;
    previous = signature;
    document.dispatchEvent(new CustomEvent("world-journal:map-preferences-change", {detail: values}));
});

export function clearSavedMapViewport() {
    try {
        localStorage.removeItem(MAP_VIEWPORT_STORAGE_KEY);
    } catch {
        // Only the last camera is browser-local; Preferences live in AppSettings.
    }
}
