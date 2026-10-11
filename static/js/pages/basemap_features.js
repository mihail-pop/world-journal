// Provider-only groups. Application country polygons and labels never enter here.
// Prefer OpenMapTiles source-layer semantics, with conservative ID fallbacks for
// styles using other schemas. Unknown layers retain their provider visibility.
export function basemapFeaturePreferences(layer) {
    const source = (layer["source-layer"] ?? "").toLowerCase();
    const id = layer.id.toLowerCase();
    const groups = [];
    if (source === "park" || /^(park|protected_area|nature_reserve)(_|$)/.test(id)) {
        groups.push("protectedAreas");
    }
    if ((source === "landcover" || source === "landuse")
        && /wood|forest|grass|wetland|scrub|vegetation/.test(`${id} ${JSON.stringify(layer.filter ?? [])}`)) {
        groups.push("vegetation");
    }
    if (layer.type === "hillshade" || /^(natural_earth|hillshade|relief)(_|$)/.test(id)) {
        groups.push("relief");
    }
    if (["water", "waterway", "water_name"].includes(source)
        || /^(water|waterway|lake|ocean|sea)(_|$)/.test(id)) {
        groups.push("water");
    }
    if (["transportation", "transportation_name", "aeroway", "aerodrome_label"].includes(source)
        || /^(road|highway|bridge|tunnel|railway|aeroway|airport)([_-]|$)/.test(id)) {
        groups.push("transport");
    }
    if (source === "building" || /^building([_-]|$)/.test(id)) groups.push("buildings");
    if (source === "landuse" && !groups.includes("vegetation")) groups.push("landUse");
    if (source === "boundary" || /^boundary([_-]|$)/.test(id)) groups.push("administrativeBorders");
    if (source === "poi" || /^poi([_-]|$)/.test(id)) groups.push("pointsOfInterest");
    if (layer.type === "symbol" && layer.layout?.["text-field"] != null) groups.push("allOtherText");
    return groups;
}
