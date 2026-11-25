const NOTICE = "Some map details could not be loaded. You can still select countries.";

export function monitorProviderResources(controller, showNotice, applyFallback) {
    const {map, notice, abortController} = controller;
    const failures = new Map();
    let timer;
    const clearNotice = () => {
        if (notice.textContent === NOTICE) showNotice(controller, "");
    };
    const refresh = () => {
        clearTimeout(timer);
        if (!failures.size) { clearNotice(); return; }
        // Brief request failures can recover while the initial view is loading.
        timer = setTimeout(() => {
            if (!abortController.signal.aborted && !controller.usingFallbackStyle && failures.size) showNotice(controller, NOTICE);
        }, 1500);
    };
    const keyFor = event => event.sourceId
        ? `${event.sourceId}:${event.tile?.tileID?.key ?? "metadata"}`
        : event.error?.url;
    const usesSource = sourceId => !sourceId.startsWith("world-journal-")
        && map.getStyle()?.layers.some(layer => layer.source === sourceId && layer.layout?.visibility !== "none");
    const reset = () => { failures.clear(); refresh(); };

    map.on("error", event => {
        if (event.error?.name === "AbortError") return;
        console.warn("World Journal map error", event.error, {source: event.sourceId, url: event.error?.url});
        if (!controller.layersInstalled) {
            // Only an actual style request failure warrants immediate fallback.
            // The existing startup timeout covers an unresponsive style request.
            if (event.error?.url === controller.providerStyleUrl) applyFallback(controller);
            return;
        }
        if (controller.usingFallbackStyle) return;
        let providerUrl = false;
        try {
            providerUrl = event.error?.url && controller.preferences.terrain
                && new URL(event.error.url).origin === new URL(controller.providerStyleUrl).origin;
        } catch { /* Errors without a request URL can still identify a source. */ }
        // Drawing/validation errors in our own layers are not provider outages.
        if (event.sourceId ? !usesSource(event.sourceId) : !providerUrl) return;
        const key = keyFor(event);
        if (key) failures.set(key, {tile: Boolean(event.tile), sourceId: event.sourceId});
        refresh();
    });
    map.on("sourcedata", event => {
        if (event.tile?.state === "loaded" || (!event.tile && event.sourceDataType === "metadata")) {
            if (failures.delete(keyFor(event))) refresh();
        }
    });
    map.on("sourcedataabort", event => { if (failures.delete(keyFor(event))) refresh(); });
    map.on("styledata", () => {
        let changed = false;
        for (const [key, failure] of failures) {
            if (failure.sourceId ? !usesSource(failure.sourceId) : !controller.preferences.terrain) changed = failures.delete(key) || changed;
        }
        if (changed) refresh();
    });
    map.on("movestart", () => {
        // A failed tile in the previous view should not mark a new view as broken.
        for (const [key, failure] of failures) if (failure.tile) failures.delete(key);
        refresh();
    });
    map.on("style.load", reset);
    abortController.signal.addEventListener("abort", () => { clearTimeout(timer); failures.clear(); }, {once: true});
}
