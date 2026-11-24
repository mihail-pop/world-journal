// Original, deterministic chart artwork. Geography always comes from the
// application's unchanged country polygons; these illustrations are decorative.
import { mapFontStack } from "./map_fonts.js";

const PREFIX = "world-journal-adventure-";
const COUNTRY_SOURCE = "world-journal-countries";
const FILL_LAYER = "world-journal-country-fill";
const OUTLINE_LAYER = "world-journal-country-outline";
const HOVER_OUTLINE_LAYER = "world-journal-country-hover-outline";
const LABEL_LAYER = "world-journal-country-names";
const palettes = {
    dark: {sea: "#29434a", ink: "#d5c49a", border: "#293b33", label: "#fae8bf", halo: "#414b3b", accent: "#efbf75", paper: "#e4cb95", vegetation: "#3c5746", shadow: "#132d30",
        land: ["#889077", "#a18a68", "#ab8b73", "#81998a", "#ae9b72", "#879d98", "#a69e83", "#939b71"]},
    light: {sea: "#9bbab4", ink: "#596e65", border: "#726048", label: "#4d4233", halo: "#ebddba", accent: "#ad5a36", paper: "#f4e7c6", vegetation: "#6e8c6c", shadow: "#4d7978",
        land: ["#dfc99a", "#c8d2aa", "#dbbea7", "#bdd1b5", "#e4cea5", "#c4d3c4", "#dfd6b6", "#d0d0a6"]},
    brown: {sea: "#6e9792", ink: "#414d3e", border: "#61553f", label: "#3d3f31", halo: "#dfc99d", accent: "#965036", paper: "#eed5aa", vegetation: "#55785c", shadow: "#315e61",
        land: ["#c6ac7d", "#afbd97", "#c5a38a", "#a6b79a", "#d2b889", "#a0b8ac", "#c7bc9b", "#bab888"]},
};

export function adventurePalette() {
    const root = document.documentElement;
    const theme = root.dataset.theme;
    const name = Object.hasOwn(palettes, theme) ? theme : getComputedStyle(root).colorScheme === "light" ? "light" : "dark";
    return {name, ...palettes[name]};
}


function drawing(size, paint) {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = size;
    const context = canvas.getContext("2d");
    paint(context, size);
    return context.getImageData(0, 0, size, size);
}

function path(context, points, fill, stroke) {
    context.beginPath();
    points.forEach(([x, y], index) => index ? context.lineTo(x, y) : context.moveTo(x, y));
    context.closePath();
    if (fill) { context.fillStyle = fill; context.fill(); }
    if (stroke) { context.strokeStyle = stroke; context.stroke(); }
}

function paper(palette) {
    return drawing(256, context => {
        let seed = 38721;
        const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
        for (let index = 0; index < 9500; index++) {
            context.fillStyle = index % 3 ? "rgba(68,52,32,.045)" : "rgba(255,249,220,.13)";
            context.fillRect(random() * 256, random() * 256, .5 + random() * 1.5, .5 + random());
        }
        context.strokeStyle = palette.border;
        context.globalAlpha = .075;
        context.lineWidth = .7;
        for (let offset = -256; offset < 512; offset += 24) {
            context.beginPath(); context.moveTo(offset, 0); context.lineTo(offset + 256, 256); context.stroke();
        }
    });
}

function waves(palette) {
    return drawing(128, context => {
        context.strokeStyle = palette.ink;
        context.lineWidth = 1.2;
        context.globalAlpha = .2;
        for (let y = 16; y <= 112; y += 32) for (let x = -32; x < 128; x += 64) {
            const offset = y % 64 === 16 ? 0 : 32;
            context.beginPath(); context.moveTo(x + offset, y);
            context.bezierCurveTo(x + offset + 8, y - 5, x + offset + 16, y - 5, x + offset + 24, y);
            context.bezierCurveTo(x + offset + 32, y + 5, x + offset + 40, y + 5, x + offset + 48, y);
            context.stroke();
            context.globalAlpha = .08;
            context.beginPath(); context.moveTo(x + offset + 5, y + 6); context.lineTo(x + offset + 23, y + 6); context.stroke();
            context.globalAlpha = .2;
        }
    });
}

function ship(palette) {
    return drawing(128, context => {
        context.lineWidth = 2; context.lineJoin = "round"; context.strokeStyle = palette.border;
        path(context, [[16,91],[113,83],[91,105],[43,110]], palette.land[1], palette.border);
        context.beginPath(); context.moveTo(65,87); context.lineTo(65,18); context.stroke();
        path(context, [[62,23],[30,80],[62,73]], palette.paper, palette.border);
        path(context, [[69,29],[104,72],[69,70]], palette.land[6], palette.border);
        path(context, [[65,18],[85,22],[65,29]], palette.accent, palette.border);
        context.strokeStyle = palette.ink; context.globalAlpha = .45;
        for (const [x,y,length] of [[20,115,39],[65,118,38],[7,102,18],[100,106,22]]) {
            context.beginPath(); context.moveTo(x,y); context.quadraticCurveTo(x+length/2,y+5,x+length,y); context.stroke();
        }
    });
}

function seaMonster(palette) {
    return drawing(128, context => {
        context.lineJoin = "round"; context.lineCap = "round"; context.lineWidth = 1.5;
        context.fillStyle = palette.vegetation; context.strokeStyle = palette.border;
        // Separate visible arches suggest a long serpent dipping underwater.
        context.beginPath(); context.moveTo(14,100); context.bezierCurveTo(19,86,12,71,20,59);
        context.quadraticCurveTo(24,50,35,55); context.lineTo(43,63); context.lineTo(30,67);
        context.bezierCurveTo(23,76,31,86,29,100); context.closePath(); context.fill(); context.stroke();
        for (const [x,width,rise] of [[43,27,42],[78,24,30]]) {
            context.beginPath(); context.moveTo(x,100); context.bezierCurveTo(x+2,100-rise,x+width-2,100-rise,x+width,100);
            context.lineTo(x+width-7,100); context.bezierCurveTo(x+width-8,100-rise*.55,x+8,100-rise*.55,x+7,100); context.closePath(); context.fill(); context.stroke();
        }
        path(context, [[111,100],[115,84],[126,75],[122,94],[118,100]], palette.vegetation, palette.border);
        path(context, [[19,59],[15,50],[24,54]], palette.land[1], palette.border);
        context.fillStyle = palette.paper; context.beginPath(); context.arc(30,59,2.5,0,Math.PI*2); context.fill();
        context.fillStyle = palette.border; context.beginPath(); context.arc(31,59,1.1,0,Math.PI*2); context.fill();
        context.strokeStyle = palette.paper; context.globalAlpha = .3;
        context.beginPath(); context.moveTo(17,96); context.quadraticCurveTo(21,77,19,69); context.stroke();
        context.strokeStyle = palette.ink; context.globalAlpha = .6;
        for (const [x,y,width] of [[5,102,30],[39,104,34],[74,102,30],[109,105,16]]) {
            context.beginPath(); context.moveTo(x,y); context.quadraticCurveTo(x+width/2,y+5,x+width,y); context.stroke();
        }
    });
}

function fantasyHeart(palette) {
    // The bundled Heroicons v2.2.0 solid heart silhouette (MIT), with original
    // pigment wash and engraved paper texture inside its existing path.
    const silhouette = new Path2D("m11.645 20.91-.007-.003-.022-.012a15.247 15.247 0 0 1-.383-.218 25.18 25.18 0 0 1-4.244-3.17C4.688 15.36 2.25 12.174 2.25 8.25 2.25 5.322 4.714 3 7.688 3A5.5 5.5 0 0 1 12 5.052 5.5 5.5 0 0 1 16.313 3c2.973 0 5.437 2.322 5.437 5.25 0 3.925-2.438 7.111-4.739 9.256a25.175 25.175 0 0 1-4.244 3.17 15.247 15.247 0 0 1-.383.219l-.022.012-.007.004-.003.001a.752.752 0 0 1-.704 0l-.003-.001Z");
    return drawing(48, context => {
        context.scale(2,2); context.save();
        const wash = context.createLinearGradient(4,3,18,22);
        wash.addColorStop(0,"#d97572"); wash.addColorStop(.55,"#ba4654"); wash.addColorStop(1,"#913342");
        context.fillStyle = wash; context.fill(silhouette); context.clip(silhouette);
        context.strokeStyle = palette.paper; context.globalAlpha = .23; context.lineWidth = .25;
        for (let x = -20; x < 40; x += 2) { context.beginPath(); context.moveTo(x,0); context.lineTo(x+24,24); context.stroke(); }
        context.fillStyle = palette.paper; context.globalAlpha = .16;
        for (let index = 0; index < 240; index++) context.fillRect((index*37%229)/10,(index*67%227)/10,.18,.28);
        context.restore(); context.strokeStyle = palette.border; context.lineWidth = .7; context.stroke(silhouette);
        context.strokeStyle = palette.paper; context.globalAlpha = .65; context.lineWidth = .25; context.stroke(silhouette);
    });
}

function compass(canvas, palette, bearing) {
    const context = canvas.getContext("2d");
    context.clearRect(0,0,256,256);
    context.save(); context.translate(128,128); context.rotate(-bearing * Math.PI / 180);
    context.strokeStyle = palette.ink; context.fillStyle = palette.ink; context.lineWidth = 1.4;
    for (const radius of [68,75]) { context.beginPath(); context.arc(0,0,radius,0,Math.PI*2); context.stroke(); }
    for (let index = 0; index < 32; index++) {
        const angle = index * Math.PI / 16;
        const inner = index % 4 ? 70 : 64;
        context.beginPath(); context.moveTo(Math.sin(angle)*inner,-Math.cos(angle)*inner); context.lineTo(Math.sin(angle)*75,-Math.cos(angle)*75); context.stroke();
    }
    for (let index = 0; index < 8; index++) {
        context.save(); context.rotate(index*Math.PI/4);
        const reach = index % 2 ? 56 : 87, width = index % 2 ? 9 : 13;
        path(context, [[0,-reach],[-width,0],[0,14],[width,0]], palette.paper, palette.ink);
        path(context, [[0,-reach],[0,14],[width,0]], palette.ink, null);
        context.restore();
    }
    context.fillStyle = palette.ink; context.beginPath(); context.arc(0,0,5,0,Math.PI*2); context.fill();
    context.font = "17px Georgia, serif"; context.textAlign = "center"; context.textBaseline = "middle";
    for (const [letter,x,y] of [["N",0,-106],["E",106,0],["S",0,106],["W",-106,0]]) context.fillText(letter,x,y);
    context.restore();
}

function illustrationData(geometry) {
    const points = [];
    const polygons = geometry.features.flatMap(feature => feature.geometry.type === "Polygon" ? [feature.geometry.coordinates] : feature.geometry.coordinates).map(polygon => {
        let west = Infinity, east = -Infinity, south = Infinity, north = -Infinity;
        for (const [x,y] of polygon[0]) { west = Math.min(west,x); east = Math.max(east,x); south = Math.min(south,y); north = Math.max(north,y); }
        return {rings:polygon,west,east,south,north};
    });
    function insideRing([x,y],ring) {
        let inside = false;
        for (let i = 0, j = ring.length-1; i < ring.length; j = i++) {
            const [xi,yi] = ring[i], [xj,yj] = ring[j];
            if ((yi > y) !== (yj > y) && x < (xj-xi)*(y-yi)/(yj-yi)+xi) inside = !inside;
        }
        return inside;
    }
    // Reject most polygons by bounds before the finer habitat check.
    const onLand = point => polygons.some(({rings,west,east,south,north}) => point[0] >= west && point[0] <= east && point[1] >= south && point[1] <= north && insideRing(point,rings[0]) && !rings.slice(1).some(ring => insideRing(point,ring)));
    const chain = (kind, coordinates, habitat = "any") => coordinates.forEach(coordinate => {
        if (habitat !== "any" && onLand(coordinate) !== (habitat === "land")) return;
        points.push({type: "Feature", properties: {kind}, geometry: {type: "Point", coordinates: coordinate}});
    });
    chain("ship", [[-36,27],[-27,-24],[68,-24],[156,18],[-143,-27]]);
    chain("sea-monster", [[-16,-16],[-158,47]],"sea");
    return {type: "FeatureCollection", features: points};
}

function smoothTrail(coordinates) {
    // Corner cutting preserves the offshore endpoints and stays inside the
    // hand-chosen control corridor, without curves overshooting onto land.
    let result = coordinates;
    for (let pass = 0; pass < 2; pass++) {
        const next = [result[0]];
        for (let index = 1; index < result.length; index++) {
            const a = result[index-1], b = result[index];
            next.push([a[0]*.75+b[0]*.25,a[1]*.75+b[1]*.25], [a[0]*.25+b[0]*.75,a[1]*.25+b[1]*.75]);
        }
        next.push(result.at(-1));
        result = next;
    }
    return result;
}

function chartData() {
    const features = [];
    for (let longitude = -180; longitude <= 180; longitude += 30) features.push({type: "Feature", properties: {kind: "grid"}, geometry: {type: "LineString", coordinates: [[longitude,-80],[longitude,80]]}});
    for (let latitude = -60; latitude <= 60; latitude += 20) features.push({type: "Feature", properties: {kind: "grid"}, geometry: {type: "LineString", coordinates: Array.from({length:37},(_,index) => [-180+index*10,latitude])}});
    const trails = [
        [[-71,32],[-59,35],[-43,39],[-29,41],[-18,40],[-11.7,37.5]],
        [[-34,-12],[-23,-22],[-8,-31],[6,-38],[18,-40],[29,-39],[42,-34],[54,-28],[68,-22],[83,-15],[96,-7]],
        // A single Pacific passage is split at the dateline so it joins the
        // repeated world copies without drawing a line across other continents.
        [[151,26],[162,30],[174,30],[180,30]],
        [[-180,30],[-169,29],[-157,26],[-147,25],[-137,26],[-127,30]],
    ];
    for (const coordinates of trails) features.push({type: "Feature", properties: {kind:"route"}, geometry: {type:"LineString", coordinates: smoothTrail(coordinates)}});
    return {type:"FeatureCollection",features};
}

export function prepareAdventure(controller, addLayer) {
    const {map} = controller;
    controller.adventurePaintKey = null;
    controller.adventureMarkerKey = null;
    const source = (name, data, options = {}) => { if (!map.getSource(PREFIX+name)) map.addSource(PREFIX+name,{type:"geojson",data,...options}); };
    controller.adventureIllustrations ||= illustrationData(controller.geometry);
    source("illustrations",controller.adventureIllustrations,{maxzoom:6});
    source("chart",chartData(),{maxzoom:6});
    source("oceans",{type:"FeatureCollection",features:[[-143,29,"NORTH PACIFIC"],[-128,-30,"SOUTH PACIFIC"],[-36,9,"ATLANTIC OCEAN"],[80,-36,"INDIAN OCEAN"]].map(([x,y,name]) => ({type:"Feature",properties:{name},geometry:{type:"Point",coordinates:[x,y]}}))},{maxzoom:5});
    const layer = (name,definition,before = FILL_LAYER) => addLayer(controller,{...definition,id:PREFIX+name,layout:{visibility:"none",...definition.layout}},before);
    // Sea detail sits beneath opaque country paint.
    layer("waves",{type:"background",paint:{"background-opacity":1}});
    layer("grid",{type:"line",source:PREFIX+"chart",maxzoom:6,filter:["==",["get","kind"],"grid"],paint:{"line-width":.65,"line-dasharray":[2,7],"line-opacity":["interpolate",["linear"],["zoom"],1,.13,4,.07,6,0]}});
    layer("routes",{type:"line",source:PREFIX+"chart",maxzoom:5,filter:["==",["get","kind"],"route"],layout:{"line-cap":"round","line-join":"round"},paint:{"line-width":1.1,"line-dasharray":[3,5],"line-opacity":["interpolate",["linear"],["zoom"],1,.3,3,.2,5,0]}});
    layer("paper",{type:"fill",source:COUNTRY_SOURCE,paint:{"fill-opacity":1}},OUTLINE_LAYER);
    const illustrationLayout = {"icon-size":["interpolate",["linear"],["zoom"],0,.26,1,.38,3,.6,5,.75],"icon-padding":2,"icon-anchor":"center","icon-allow-overlap":true,"icon-ignore-placement":true};
    layer("illustrations",{type:"symbol",source:PREFIX+"illustrations",layout:illustrationLayout,paint:{"icon-opacity":1}},HOVER_OUTLINE_LAYER);
    layer("ocean-names",{type:"symbol",source:PREFIX+"oceans",maxzoom:5,layout:{"text-field":["get","name"],"text-font":mapFontStack(),"text-size":["interpolate",["linear"],["zoom"],1,11,3,16],"text-letter-spacing":.22,"text-max-width":20},paint:{"text-opacity":["interpolate",["linear"],["zoom"],1,.65,3,.6,5,0]}},LABEL_LAYER);
}

export function updateAdventure(controller, active, palette = adventurePalette()) {
    const {map} = controller;
    controller.page.dataset.mapType = controller.preferences.mapType;
    controller.container.setAttribute("aria-label", active ? "Interactive adventure world map" : "Interactive world map");
    for (const name of ["waves","grid","routes","paper","illustrations","ocean-names"]) {
        const id = PREFIX+name;
        if (!map.getLayer(id)) continue;
        const visible = active && (name !== "ocean-names" || controller.preferences.countryNames);
        if (map.getLayoutProperty(id,"visibility") !== (visible ? "visible" : "none")) map.setLayoutProperty(id,"visibility",visible ? "visible" : "none");
    }
    if (!active) { updateAdventureMarkers(controller,false,palette); return; }
    if (controller.adventurePaintKey !== palette.name || !map.hasImage(PREFIX+"paper-"+palette.name)) {
        controller.adventurePaintKey = palette.name;
        controller.adventureImages ||= new Map();
        for (const [name, painter] of Object.entries({paper,waves,ship,"sea-monster":seaMonster,"favorite-heart":fantasyHeart})) {
            const id = PREFIX+name+"-"+palette.name;
            if (!map.hasImage(id)) {
                const image = controller.adventureImages.get(id) || painter(palette);
                controller.adventureImages.set(id,image);
                map.addImage(id,image,{pixelRatio:2});
            }
        }
        map.setPaintProperty(PREFIX+"waves","background-pattern",PREFIX+"waves-"+palette.name);
        map.setPaintProperty(PREFIX+"paper","fill-pattern",PREFIX+"paper-"+palette.name);
        map.setLayoutProperty(PREFIX+"illustrations","icon-image",["concat",PREFIX,["get","kind"],"-"+palette.name]);
        for (const name of ["grid","routes"]) map.setPaintProperty(PREFIX+name,"line-color",palette.ink);
        map.setPaintProperty(PREFIX+"ocean-names","text-color",palette.ink);
        map.setPaintProperty(PREFIX+"ocean-names","text-halo-color",palette.sea);
        map.setPaintProperty(PREFIX+"ocean-names","text-halo-width",1);
    }
    updateAdventureMarkers(controller,true,palette);
    const canvas = controller.page.querySelector("[data-adventure-compass]");
    const key = `${palette.name}:${map.getBearing()}`;
    if (canvas.dataset.paintKey !== key) { compass(canvas,palette,map.getBearing()); canvas.dataset.paintKey = key; }
}

function updateAdventureMarkers(controller, active, palette) {
    const {map} = controller;
    const favoriteLayer = "world-journal-country-favorites";
    const markerKey = active ? palette.name : "standard";
    if (controller.adventureMarkerKey === markerKey) return;
    controller.adventureMarkerKey = markerKey;
    if (map.getLayer(favoriteLayer)) {
        const image = active ? PREFIX+"favorite-heart-"+palette.name : "world-journal-favorite-heart";
        if (map.hasImage(image)) map.setLayoutProperty(favoriteLayer,"icon-image",image);
        // Anchor the visible tip; the 24px silhouette has 3px of space below it.
        map.setLayoutProperty(favoriteLayer,"icon-anchor","bottom");
        map.setLayoutProperty(favoriteLayer,"icon-offset",[0,3]);
    }
}
