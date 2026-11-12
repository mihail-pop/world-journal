import { isBasemapCapitalLabel, isBasemapCountryLabel, splitBasemapRegionLabels } from "./basemap_features.js";
import { mapFontStack } from "./map_fonts.js";

export function ensurePlaceLabels(controller, onReady, onError) {
    if (!controller.layersInstalled || controller.usingFallbackStyle || controller.placeLabelsRequest
        || (!controller.preferences.cityNames && !controller.preferences.regionNames)
        || controller.basemapLayers.some(layer => layer["source-layer"] === "place")
        || Date.now() - (controller.placeLabelsFailedAt ?? 0) < 30000) return;
    const {map, styleGeneration} = controller;
    controller.placeLabelsRequest = true;
    // Optional place labels arrive after the bundled map is usable. Import only
    // place symbols and their vector source, never terrain imagery or sprites.
    (async () => {
        const response = await fetch(controller.providerStyleUrl, {signal: controller.abortController.signal});
        if (!response.ok) throw new Error(`Place-label style returned HTTP ${response.status}`);
        const style = await response.json();
        if (controller.abortController.signal.aborted || controller.styleGeneration !== styleGeneration) return;
        const layers = style.layers.filter(layer => layer.type === "symbol" && layer["source-layer"] === "place"
            && !isBasemapCountryLabel(layer) && !isBasemapCapitalLabel(layer));
        for (const sourceId of new Set(layers.map(layer => layer.source))) {
            if (map.getSource(sourceId)) continue;
            const source = {...style.sources[sourceId]};
            if (source.url) source.url = new URL(source.url, controller.providerStyleUrl).href;
            if (source.tiles) source.tiles = source.tiles.map(url => new URL(url, controller.providerStyleUrl).href);
            map.addSource(sourceId, source);
        }
        for (const layer of layers) {
            if (map.getLayer(layer.id)) continue;
            const layout = {...layer.layout, "text-font": mapFontStack(layer.layout?.["text-font"])};
            map.addLayer({...layer, layout}, "world-journal-country-names");
        }
        splitBasemapRegionLabels(map);
        controller.placeLabelsRequest = false;
        onReady();
    })().catch(error => {
        if (controller.abortController.signal.aborted || controller.styleGeneration !== styleGeneration) return;
        controller.placeLabelsFailedAt = Date.now();
        onError(error);
    }).finally(() => { controller.placeLabelsRequest = false; });
}
