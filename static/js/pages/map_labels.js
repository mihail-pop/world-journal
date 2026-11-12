import { isBasemapCityLabel } from "./basemap_features.js";
import { mapFontStack } from "./map_fonts.js";

export function terrainCountrySize(scale = 1) {
    return ["interpolate", ["linear"], ["zoom"], 1, 12 * scale, 5, 18 * scale];
}

const CAPITAL_SIZE = ["interpolate", ["linear"], ["zoom"], 2.5, 12, 7, 16];
const CITY_SIZE = ["interpolate", ["linear"], ["zoom"], 3, 10.5, 7, 14, 11, 15];
const SIMPLE_CITY_SIZE = ["interpolate", ["linear"], ["zoom"], 3, 9, 7, 11, 11, 11.5];
const TERRAIN_COLORS = {country: "#202124", place: "#34363a", halo: "#ffffff"};

function pointImage(map, kind, colors) {
    const id = `world-journal-${kind}-point-${colors.place}-${colors.halo}`;
    if (!map.hasImage(id)) {
        // Draw crisp local concentric circles; no sprite service is needed.
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = 24;
        const context = canvas.getContext("2d");
        context.scale(2, 2);
        context.beginPath();
        context.arc(6, 6, 4.5, 0, 2 * Math.PI);
        context.fillStyle = colors.halo;
        context.fill();
        context.strokeStyle = colors.place;
        context.lineWidth = kind === "city" ? 2 : 1.2;
        context.stroke();
        if (kind === "capital") {
            context.beginPath();
            context.arc(6, 6, 2, 0, 2 * Math.PI);
            context.fillStyle = colors.place;
            context.fill();
        }
        map.addImage(id, context.getImageData(0, 0, 24, 24), {pixelRatio: 2});
    }
    return id;
}

function replaceCityPoint(value, image) {
    if (value === "circle_11_black") return image;
    return Array.isArray(value) ? value.map(part => replaceCityPoint(part, image)) : value;
}

export function updateMapLabels(controller, layers, {terrain, adventure, foreground, background}) {
    const {map} = controller;
    const colors = terrain ? TERRAIN_COLORS : {country: foreground, place: foreground, halo: background};
    for (const layer of [layers.countryNames, layers.hoverCountryName]) {
        map.setPaintProperty(layer, "text-color", colors.country);
        map.setPaintProperty(layer, "text-halo-color", colors.halo);
    }
    // Retain a state expression across modes to keep loaded symbol bindings valid.
    map.setPaintProperty(layers.countryNames, "text-opacity",
        ["case", ["boolean", ["feature-state", "hoverLabel"], false], terrain ? 0 : 1, 1]);
    map.setPaintProperty(layers.capitalMarkers, "circle-color", foreground);
    map.setPaintProperty(layers.capitalMarkers, "circle-stroke-color", background);
    map.setPaintProperty(layers.capitalNames, "text-color", colors.place);
    map.setPaintProperty(layers.capitalNames, "text-halo-color", colors.halo);
    controller.hoverName.style.setProperty("--map-label-color", colors.country);
    controller.hoverName.style.setProperty("--map-label-halo", colors.halo);

    const layoutKey = terrain ? "terrain" : adventure ? "adventure" : "simple";
    if (controller.labelLayoutKey !== layoutKey) {
        controller.labelLayoutKey = layoutKey;
        map.setLayoutProperty(layers.countryNames, "text-font", mapFontStack(adventure ? "Regular" : "Bold"));
        map.setLayoutProperty(layers.countryNames, "text-transform", adventure ? "uppercase" : "none");
        map.setLayoutProperty(layers.countryNames, "text-letter-spacing", adventure ? .07 : 0);
        map.setLayoutProperty(layers.countryNames, "text-size", terrain ? terrainCountrySize()
            : ["interpolate", ["linear"], ["zoom"], 1, adventure ? 10 : 9, 5, adventure ? 16 : 14]);
        map.setLayoutProperty(layers.capitalNames, "text-font", mapFontStack(terrain ? "Medium" : "Regular"));
        map.setLayoutProperty(layers.capitalNames, "text-size", terrain ? CAPITAL_SIZE
            : ["interpolate", ["linear"], ["zoom"], 2.5, 9, 7, 12]);
        map.setLayoutProperty(layers.capitalNames, "text-anchor", terrain ? "left" : "top");
        map.setLayoutProperty(layers.capitalNames, "text-offset", terrain ? [.6, 0] : [0, .55]);
        map.setLayoutProperty(layers.capitalNames, "icon-size", .8);
        map.setLayoutProperty(layers.capitalNames, "text-optional", !terrain);
    }
    const capitalPoint = terrain ? pointImage(map, "capital", colors) : "";
    if (map.getLayoutProperty(layers.capitalNames, "icon-image") !== capitalPoint) {
        map.setLayoutProperty(layers.capitalNames, "icon-image", capitalPoint);
    }
    const cityPoint = pointImage(map, "city", colors);
    for (const layer of controller.basemapLayers.filter(isBasemapCityLabel)) {
        map.setPaintProperty(layer.id, "text-color", colors.place);
        map.setPaintProperty(layer.id, "text-halo-color", colors.halo);
        map.setPaintProperty(layer.id, "text-halo-width", 1.25);
        if (controller.cityLabelLayoutKey !== layoutKey) {
            map.setLayoutProperty(layer.id, "text-size", terrain ? CITY_SIZE : SIMPLE_CITY_SIZE);
            map.setLayoutProperty(layer.id, "text-anchor", "left");
            map.setLayoutProperty(layer.id, "text-offset", [.5, 0]);
            map.setLayoutProperty(layer.id, "icon-size", .5);
        }
        if (!controller.cityLabelLayoutsInstalled) {
            // Some capitals are classified as towns or villages. Keep those
            // under Capital names rather than showing a second provider label.
            map.setFilter(layer.id, ["all", layer.filter ?? true, ["!=", ["get", "capital"], 2]]);
        }
        if (layer.layout["icon-image"] != null) {
            map.setLayoutProperty(layer.id, "icon-image", replaceCityPoint(layer.layout["icon-image"], cityPoint));
        }
    }
    for (const layer of controller.basemapLayers) {
        const groups = controller.basemapFeatureGroups.get(layer.id);
        if (groups.includes("regionNames")) {
            map.setPaintProperty(layer.id, "text-color", colors.place);
            map.setPaintProperty(layer.id, "text-halo-color", colors.halo);
        }
    }
    controller.cityLabelLayoutsInstalled = true;
    controller.cityLabelLayoutKey = layoutKey;
}
