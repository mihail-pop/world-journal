// A territory edit updates retained screens without rebuilding the map canvas.
import { notify } from "./notifications.js";
let registered = false;
let pending = null;

export function registerCountryMetadata() {
    if (registered) return;
    registered = true;
    document.addEventListener("world-journal:data-changed", async event => {
        const path = event.detail?.path || "";
        if (!path.endsWith("/territory/") && !path.startsWith("/settings/backups/")) return;
        pending?.abort();
        const abort = pending = new AbortController();
        const timeout = setTimeout(() => abort.abort(), 10000);
        try {
            const response = await fetch("/data/countries.json", {signal: abort.signal, cache: "no-store"});
            if (!response.ok) throw new Error("Metadata unavailable");
            const metadata = await response.json();
            if (!Array.isArray(metadata.countries) || pending !== abort) return;
            document.dispatchEvent(new CustomEvent("world-journal:country-metadata-changed", {detail: metadata}));
        } catch (error) {
            if (error.name !== "AbortError") notify({id: "territory-display-update", kind: "warning", title: "Details saved", message: "Refresh the page to update the retained map labels."});
        }
        finally { clearTimeout(timeout); if (pending === abort) pending = null; }
    });
}
