// Provider-only groups. Application country polygons and labels never enter here.
// Prefer OpenMapTiles source-layer semantics, with conservative ID fallbacks for
// styles using other schemas. Unknown layers retain their provider visibility.
const REGION_CLASSES = ["state", "province", "region", "county", "district", "prefecture"];

function matchesProperty(filter, property, values) {
    if (!Array.isArray(filter)) return false;
    const [operator, field, value] = filter;
    if (operator === "all") return filter.slice(1).some(part => matchesProperty(part, property, values));
    return operator === "==" && (field === property || (
        Array.isArray(field) && field[0] === "get" && field[1] === property
    )) && values.includes(value);
}

export function isBasemapCapitalLabel(layer) {
    if (layer.type !== "symbol") return false;
    return /(^|[_-])capital([_-]|$)/i.test(layer.id) || (layer["source-layer"] === "place" && (
        matchesProperty(layer.filter, "capital", [2]) || matchesProperty(layer.filter, "adm0cap", [1, true])
    ));
}

export function isBasemapCountryLabel(layer) {
    return layer.type === "symbol" && (/(^|[_-])country([_-]|$)/i.test(layer.id)
        || (layer["source-layer"] === "place" && matchesProperty(layer.filter, "class", ["country"])));
}

export function isBasemapCityLabel(layer) {
    if (layer.type !== "symbol" || layer.layout?.["text-field"] == null || isBasemapCapitalLabel(layer)) return false;
    return /(^|[_-])(city|town|village)([_-]|$)/i.test(layer.id) || (layer["source-layer"] === "place"
        && matchesProperty(layer.filter, "class", ["city", "town", "village"]));
}

function isBasemapRegionLabel(layer) {
    if (layer.type !== "symbol" || layer.layout?.["text-field"] == null) return false;
    return /(^|[_-])(state|province|region|county|district|prefecture)([_-]|$)/i.test(layer.id)
        || (layer["source-layer"] === "place" && matchesProperty(layer.filter, "class", REGION_CLASSES));
}

export function splitBasemapRegionLabels(map) {
    // Liberty's generic place layer also contains provinces. Partition mixed
    // layers once per style so regions and other labels have separate controls,
    // while reusing the same provider tiles, text styling and zoom limits.
    for (const layer of map.getStyle().layers) {
        if (layer["source-layer"] !== "place" || layer.type !== "symbol" || layer.layout?.["text-field"] == null
            || isBasemapCountryLabel(layer) || isBasemapCapitalLabel(layer)
            || isBasemapCityLabel(layer) || isBasemapRegionLabel(layer)) continue;
        const id = `${layer.id}_region`;
        if (map.getLayer(id)) continue;
        const regional = ["in", ["get", "class"], ["literal", REGION_CLASSES]];
        map.setFilter(layer.id, ["all", layer.filter ?? true, ["!", regional]]);
        map.addLayer({...layer, id, filter: ["all", layer.filter ?? true, regional]}, layer.id);
    }
}

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
    if (isBasemapCityLabel(layer)) groups.push("cityNames");
    else if (isBasemapRegionLabel(layer)) groups.push("regionNames");
    else if (layer.type === "symbol" && layer.layout?.["text-field"] != null) groups.push("allOtherText");
    return groups;
}
