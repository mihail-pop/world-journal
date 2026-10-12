import { notify } from "../notifications.js";
import {
    clearSavedMapViewport,
    MAP_BOOLEAN_PREFERENCES,
    readMapPreferences,
    writeMapPreferences,
} from "../map_preferences.js";

let lifecycleRegistered = false;
let activeController = null;
let activeInformationController = null;

async function loadCountries(url, signal) {
    const response = await fetch(url, { signal });
    if (!response.ok) {
        throw new Error(`${url} returned HTTP ${response.status}`);
    }
    const metadata = await response.json();
    if (!Array.isArray(metadata.countries)) {
        throw new Error("Bundled country metadata has an invalid schema");
    }
    return metadata.countries;
}

function setStatus(controller, message, isError = false) {
    controller.status.textContent = message;
    controller.status.hidden = !message;
    controller.status.classList.toggle("is-error", isError);
}

async function initializeSettingsPage() {
    const page = document.querySelector('[data-page="settings"]');
    if (!page || !page.querySelector("[data-home-country-select]") || activeController?.page === page) {
        return;
    }
    cleanupSettingsPage();
    const controller = {
        page,
        abortController: new AbortController(),
        select: page.querySelector("[data-home-country-select]"),
        status: page.querySelector("[data-settings-status]"),
    };
    activeController = controller;

    try {
        const countries = await loadCountries(
            page.dataset.countryMetadataUrl,
            controller.abortController.signal,
        );
        if (activeController !== controller) {
            return;
        }
        const sortedCountries = countries.toSorted((first, second) => (
            first.name.localeCompare(second.name, "en")
        ));
        const validCountryCodes = new Set(sortedCountries.map((country) => country.iso_a2));
        const fragment = document.createDocumentFragment();
        for (const country of sortedCountries) {
            fragment.append(new Option(country.name, country.iso_a2));
        }
        controller.select.append(fragment);
        const preferences = readMapPreferences(validCountryCodes);
        controller.preferences = preferences;
        controller.select.value = preferences.homeCountry ?? "";
        controller.select.disabled = false;
        const mapType = page.querySelector("[data-settings-map-type]");
        mapType.value = preferences.mapType;
        mapType.disabled = false;
        mapType.dispatchEvent(new Event("change", {bubbles: true}));
        mapType.addEventListener("change", () => {
            if (mapType.value === controller.preferences.mapType) return;
            writeMapPreferences({...controller.preferences, mapType: mapType.value}, validCountryCodes, {notifySaved: true});
        }, {signal: controller.abortController.signal});
        const labelChoices = page.querySelectorAll("[data-settings-map-preference]");
        const preferenceKeys = new Set(MAP_BOOLEAN_PREFERENCES);
        for (const input of labelChoices) {
            input.checked = preferences[input.dataset.settingsMapPreference];
            input.disabled = false;
            input.addEventListener("change", () => {
                const key = input.dataset.settingsMapPreference;
                if (!preferenceKeys.has(key)) return;
                writeMapPreferences({ ...readMapPreferences(validCountryCodes), [key]: input.checked }, validCountryCodes, {notifySaved: true});
            }, { signal: controller.abortController.signal });
        }
        document.addEventListener("world-journal:map-preferences-change", event => {
            controller.preferences = event.detail;
            mapType.value = event.detail.mapType;
            mapType.dispatchEvent(new Event("change"));
            for (const input of labelChoices) {
                input.checked = Boolean(event.detail[input.dataset.settingsMapPreference]);
            }
        }, { signal: controller.abortController.signal });
        setStatus(controller, "");

        controller.select.addEventListener("change", () => {
            const current = readMapPreferences(validCountryCodes);
            const requestedCode = controller.select.value;
            const homeCountry = validCountryCodes.has(requestedCode) ? requestedCode : null;
            if (homeCountry !== current.homeCountry) {
                clearSavedMapViewport();
            }
            writeMapPreferences({ ...current, homeCountry }, validCountryCodes, {notifySaved: true});
        }, { signal: controller.abortController.signal });
    } catch (error) {
        if (error.name === "AbortError") {
            return;
        }
        setStatus(controller, "Home-country options could not be loaded.", true);
        notify({id: "settings-load-error", kind: "error", title: "Country options are unavailable", message: "Reload Settings when the server is available. Your saved home country is kept."});
        console.error("World Journal settings initialization failed", error);
    }
}

async function initializeInformationPage() {
    const page = document.querySelector('[data-page="settings"]');
    const section = page?.querySelector("[data-version-information]");
    if (!section || activeInformationController?.page === page) return;
    activeInformationController?.abortController.abort();
    const controller = {page, abortController: new AbortController()};
    activeInformationController = controller;
    const latest = section.querySelector("[data-latest-release]");
    const status = section.querySelector("[data-version-status]");
    try {
        const response = await fetch(section.dataset.versionInfoUrl, {signal: controller.abortController.signal});
        if (!response.ok) throw new Error(`Version information returned HTTP ${response.status}`);
        const data = await response.json();
        if (activeInformationController !== controller) return;
        latest.textContent = data.latest_version || "Unable to check";
        latest.href = data.latest_url;
        status.href = data.latest_url;
        status.textContent = data.is_latest === true
            ? "You have the latest version"
            : data.is_latest === false ? "Update available" : "View releases";
        status.classList.toggle("is-current", data.is_latest === true);
        status.classList.toggle("is-update", data.is_latest === false);
    } catch (error) {
        if (error.name === "AbortError") return;
        latest.textContent = "Unable to check";
        status.textContent = "View releases";
        console.error("World Journal version check failed", error);
    }
}

export function cleanupSettingsPage() {
    if (activeController) {
        activeController.abortController.abort();
        activeController = null;
    }
    if (activeInformationController) {
        activeInformationController.abortController.abort();
        activeInformationController = null;
    }
}

export function registerSettingsPage() {
    if (lifecycleRegistered) {
        return;
    }
    lifecycleRegistered = true;
    document.addEventListener("world-journal:page-ready", (event) => {
        if (event.detail.page === "settings") {
            initializeSettingsPage();
            initializeInformationPage();
        }
    });
    document.addEventListener("world-journal:page-cleanup", cleanupSettingsPage);
}
