import { beginTask, notify } from "../notifications.js";
import { readAppPreferences, writeAppPreferences } from "../app_preferences.js";
import {
    clearSavedMapViewport,
    MAP_BOOLEAN_PREFERENCES,
    readMapPreferences,
    writeMapPreferences,
} from "../map_preferences.js";

let lifecycleRegistered = false;
let activeController = null;
let versionInformation = null;
let versionExpiresAt = 0;
let versionRequest = null;
let backupExportPending = false;

async function createBackup(button) {
    if (backupExportPending) return;
    backupExportPending = true;
    button.setAttribute("aria-disabled", "true");
    const finish = beginTask("Creating backup…");
    try {
        const response = await fetch(button.href, {headers: {"Accept": "application/zip"}});
        if (!response.ok || !response.headers.get("Content-Type")?.startsWith("application/zip")) {
            const result = await response.json().catch(() => null);
            throw new Error(result?.error || "Check that the server is running and try again.");
        }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const download = document.createElement("a");
        download.href = url;
        download.download = response.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] || "world-journal-backup.zip";
        download.setAttribute("hx-boost", "false");
        document.body.append(download);
        download.click();
        download.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
        notify({id: "backup-export", kind: "success", title: "Backup ready", message: "The ZIP file is ready to save."});
    } catch (error) {
        notify({id: "backup-export", kind: "error", title: "Backup could not be created", message: error.message});
    } finally {
        finish();
        backupExportPending = false;
        button.removeAttribute("aria-disabled");
    }
}

function initializeAppFont() {
    const select = document.querySelector("[data-app-font]");
    if (!select) return;
    select.value = readAppPreferences().font;
    select.disabled = false;
    select.dispatchEvent(new Event("change"));
}

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
            controller.select.value = event.detail.homeCountry ?? "";
            controller.select.dispatchEvent(new Event("change"));
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

function renderVersionInformation(section, data) {
    if (!section?.isConnected) return;
    const latest = section.querySelector("[data-latest-release]");
    const status = section.querySelector("[data-version-status]");
    latest.textContent = data?.latest_version || "Unable to check";
    if (data?.latest_url) latest.href = data.latest_url;
    if (data?.releases_url) status.href = data.releases_url;
    status.textContent = data?.is_latest === true ? "✓ You have the latest version" : data?.is_latest === false ? "↻ Update available" : "";
    status.hidden = typeof data?.is_latest !== "boolean";
    status.classList.toggle("is-current", data?.is_latest === true);
    status.classList.toggle("is-update", data?.is_latest === false);
}

function loadVersionInformation(url) {
    if (Date.now() < versionExpiresAt) return Promise.resolve(versionInformation);
    if (!versionRequest) {
        versionRequest = fetch(url).then(async response => {
            if (!response.ok) throw new Error(`Version information returned HTTP ${response.status}`);
            const data = await response.json();
            if (!data || typeof data.current_version !== "string") throw new Error("Invalid version information");
            versionInformation = data;
            versionExpiresAt = Date.now() + (data.latest_version ? 15 * 60 * 1000 : 60 * 1000);
            return data;
        }).catch(() => {
            if (versionInformation) {
                versionInformation = {...versionInformation, latest_version: null, latest_url: versionInformation.releases_url, is_latest: null};
            }
            versionExpiresAt = Date.now() + 60 * 1000;
            return versionInformation;
        }).finally(() => { versionRequest = null; });
    }
    return versionRequest;
}

function initializeInformationPage() {
    const page = document.querySelector('[data-page="settings"]');
    const url = page?.querySelector("[data-version-info-url]")?.dataset.versionInfoUrl;
    if (!url) return;
    const section = page?.querySelector("[data-version-information]");
    if (versionInformation) renderVersionInformation(section, versionInformation);
    // Share one request across tabs; visiting Settings warms the result for Information.
    void loadVersionInformation(url).then(data => renderVersionInformation(section, data));
}

export function cleanupSettingsPage() {
    if (activeController) {
        activeController.abortController.abort();
        activeController = null;
    }
}

export function registerSettingsPage() {
    if (lifecycleRegistered) {
        return;
    }
    lifecycleRegistered = true;
    document.addEventListener("click", event => {
        const create = event.target.closest("[data-backup-create]");
        if (create) {
            event.preventDefault();
            void createBackup(create);
            return;
        }
        const button = event.target.closest("[data-backup-open]");
        if (!button) return;
        const input = button.closest("[data-backup-upload]").querySelector('input[type="file"]');
        input.value = "";
        input.click();
    });
    document.addEventListener("change", event => {
        if (event.target.matches('[data-backup-upload] input[type="file"]')) {
            if (event.target.files.length) event.target.form.requestSubmit();
            return;
        }
        if (!event.target.matches("[data-app-font]")) return;
        writeAppPreferences({font: event.target.value}, {notifySaved: true});
    });
    document.addEventListener("world-journal:app-preferences-change", initializeAppFont);
    document.addEventListener("world-journal:page-ready", (event) => {
        if (event.detail.page === "settings") {
            initializeAppFont();
            initializeSettingsPage();
            initializeInformationPage();
        }
    });
    document.addEventListener("world-journal:page-cleanup", cleanupSettingsPage);
}
