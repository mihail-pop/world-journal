import { readAppPreferences, writeAppPreferences } from "./app_preferences.js";

export const MAP_VIEWPORT_STORAGE_KEY = "world-journal:map-viewport";

export const DEFAULT_MAP_PREFERENCES = Object.freeze({
    homeCountry: null, countryNames: true, capitalNames: false, cityNames: true,
    regionNames: false, smallCountryMarkers: false, terrain: true, mapType: "terrain",
    allOtherText: true, protectedAreas: false, vegetation: true, relief: true,
    water: true, transport: true, buildings: false, landUse: false,
    administrativeBorders: true, pointsOfInterest: false,
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
    for (const key of [...MAP_BOOLEAN_PREFERENCES, "mapType", "homeCountry"]) {
        if (next[key] !== current[key]) patch[key] = next[key];
    }
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
