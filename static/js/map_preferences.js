export const MAP_PREFERENCES_VERSION = 2;
export const MAP_PREFERENCES_STORAGE_KEY = "world-journal:map-preferences:v2";
const LEGACY_MAP_PREFERENCES_STORAGE_KEY = "world-journal:map-preferences:v1";
export const MAP_VIEWPORT_STORAGE_KEY = "world-journal:map-viewport";

export const DEFAULT_MAP_PREFERENCES = Object.freeze({
    version: MAP_PREFERENCES_VERSION,
    homeCountry: null,
    countryNames: true,
    capitalNames: false,
    terrain: true,
    allOtherText: true,
});

const BOOLEAN_PREFERENCES = [
    "countryNames",
    "capitalNames",
    "terrain",
    "allOtherText",
];

function normalizePreferences(value, validCountryCodes) {
    const normalized = { ...DEFAULT_MAP_PREFERENCES };
    if (!value || typeof value !== "object" || ![1, MAP_PREFERENCES_VERSION].includes(value.version)) {
        return normalized;
    }
    if (value.version === 1) {
        normalized.terrain = value.simpleMode !== true;
    }
    for (const key of BOOLEAN_PREFERENCES) {
        if (value.version === MAP_PREFERENCES_VERSION && typeof value[key] === "boolean") {
            normalized[key] = value[key];
        } else if (["countryNames", "capitalNames"].includes(key) && typeof value[key] === "boolean") {
            normalized[key] = value[key];
        }
    }
    const homeCountry = typeof value.homeCountry === "string"
        ? value.homeCountry.trim().toUpperCase()
        : null;
    if (homeCountry && validCountryCodes?.has(homeCountry)) {
        normalized.homeCountry = homeCountry;
    }
    return normalized;
}

export function readMapPreferences(validCountryCodes) {
    try {
        const saved = localStorage.getItem(MAP_PREFERENCES_STORAGE_KEY)
            ?? localStorage.getItem(LEGACY_MAP_PREFERENCES_STORAGE_KEY);
        return normalizePreferences(
            JSON.parse(saved),
            validCountryCodes,
        );
    } catch (error) {
        return { ...DEFAULT_MAP_PREFERENCES };
    }
}

export function writeMapPreferences(value, validCountryCodes) {
    const normalized = normalizePreferences(value, validCountryCodes);
    try {
        localStorage.setItem(MAP_PREFERENCES_STORAGE_KEY, JSON.stringify(normalized));
    } catch (error) {
        // Preferences remain active for the current page when storage is unavailable.
    }
    return normalized;
}

export function clearSavedMapViewport() {
    try {
        localStorage.removeItem(MAP_VIEWPORT_STORAGE_KEY);
    } catch (error) {
        // The active page remains usable when storage is unavailable.
    }
}