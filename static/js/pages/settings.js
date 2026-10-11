import {
    clearSavedMapViewport,
    readMapPreferences,
    writeMapPreferences,
} from "../map_preferences.js";

let lifecycleRegistered = false;
let activeController = null;

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
        controller.select.value = preferences.homeCountry ?? "";
        controller.select.disabled = false;
        setStatus(controller, "");

        controller.select.addEventListener("change", () => {
            const current = readMapPreferences(validCountryCodes);
            const requestedCode = controller.select.value;
            const homeCountry = validCountryCodes.has(requestedCode) ? requestedCode : null;
            if (homeCountry !== current.homeCountry) {
                clearSavedMapViewport();
            }
            writeMapPreferences({ ...current, homeCountry }, validCountryCodes);
            const selectedCountry = sortedCountries.find((country) => country.iso_a2 === homeCountry);
            setStatus(
                controller,
                selectedCountry ? `Home country saved as ${selectedCountry.name}.` : "Home country cleared.",
            );
        }, { signal: controller.abortController.signal });
    } catch (error) {
        if (error.name === "AbortError") {
            return;
        }
        setStatus(controller, "Home-country options could not be loaded.", true);
        console.error("World Journal settings initialization failed", error);
    }
}

export function cleanupSettingsPage() {
    if (!activeController) {
        return;
    }
    activeController.abortController.abort();
    activeController = null;
}

export function registerSettingsPage() {
    if (lifecycleRegistered) {
        return;
    }
    lifecycleRegistered = true;
    document.addEventListener("world-journal:page-ready", (event) => {
        if (event.detail.page === "settings") {
            initializeSettingsPage();
        }
    });
    document.addEventListener("world-journal:page-cleanup", cleanupSettingsPage);
}
