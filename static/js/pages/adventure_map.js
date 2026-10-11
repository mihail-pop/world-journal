// Original, deterministic chart artwork. Geography always comes from the
// application's unchanged country polygons; these illustrations are decorative.
const PREFIX = "world-journal-adventure-";
const COUNTRY_SOURCE = "world-journal-countries";
const FILL_LAYER = "world-journal-country-fill";
const OUTLINE_LAYER = "world-journal-country-outline";
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
    const theme = document.documentElement.dataset.theme;
    return {name: theme in palettes ? theme : "dark", ...(palettes[theme] || palettes.dark)};
}

function hash(text) {
    let value = 2166136261;
    for (const char of text) value = Math.imul(value ^ char.charCodeAt(0), 16777619);
    return value >>> 0;
}

function topology(geometry) {
    const edges = new Map();
    const rings = [];
    const neighbors = new Map();
    const key = (a, b) => {
        const first = a.join(","), second = b.join(",");
        return first < second ? `${first}/${second}` : `${second}/${first}`;
    };
    for (const feature of geometry.features) {
        const code = feature.properties.iso_a2;
        neighbors.set(code, new Set());
        const polygons = feature.geometry.type === "Polygon" ? [feature.geometry.coordinates] : feature.geometry.coordinates;
        for (const polygon of polygons) for (const ring of polygon) {
            rings.push(ring);
            for (let index = 1; index < ring.length; index++) {
                const id = key(ring[index - 1], ring[index]);
                if (!edges.has(id)) edges.set(id, new Set());
                edges.get(id).add(code);
            }
        }
    }
    for (const owners of edges.values()) if (owners.size > 1) {
        for (const first of owners) for (const second of owners) if (first !== second) neighbors.get(first).add(second);
    }
    const coast = [];
    for (const ring of rings) {
        let run = [];
        for (let index = 1; index < ring.length; index++) {
            const a = ring[index - 1], b = ring[index];
            const seam = Math.abs(a[0] - b[0]) > 180 || Math.abs(a[0]) === 180 && Math.abs(b[0]) === 180;
            if (!seam && edges.get(key(a, b)).size === 1) {
                if (!run.length) run.push(a);
                run.push(b);
            } else if (run.length) { coast.push(run); run = []; }
        }
        if (run.length) coast.push(run);
    }
    // Greedy graph coloring gives shared-border neighbors different paper hues.
    const colors = new Map();
    const codes = [...neighbors.keys()].sort((a, b) => neighbors.get(b).size - neighbors.get(a).size || a.localeCompare(b));
    for (const code of codes) {
        const used = new Set([...neighbors.get(code)].map(other => colors.get(other)));
        const preferred = hash(code) % 8;
        const index = Array.from({length: 8}, (_, offset) => (preferred + offset) % 8).find(candidate => !used.has(candidate));
        colors.set(code, index ?? preferred);
    }
    return {colors, coast: {type: "Feature", properties: {}, geometry: {type: "MultiLineString", coordinates: coast}}};
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

function mountain(palette) {
    return drawing(128, context => {
        context.lineJoin = "round"; context.lineCap = "round"; context.lineWidth = 1.5;
        context.fillStyle = palette.shadow; context.globalAlpha = .12;
        context.beginPath(); context.ellipse(64, 103, 55, 8, 0, 0, Math.PI * 2); context.fill();
        context.globalAlpha = 1;
        path(context, [[7,100],[35,52],[67,103]], palette.land[1], palette.border);
        path(context, [[40,103],[86,39],[123,102]], palette.land[6], palette.border);
        path(context, [[21,105],[62,19],[101,105]], palette.paper, palette.border);
        path(context, [[62,19],[62,105],[101,105]], palette.land[1], null);
        path(context, [[48,48],[62,19],[76,48],[66,42],[61,50],[56,42]], palette.paper, palette.border);
        context.strokeStyle = palette.border; context.globalAlpha = .45;
        for (let y = 60; y < 98; y += 7) {
            context.beginPath(); context.moveTo(66, y); context.lineTo(66 + (y - 30) * .35, y + 6); context.stroke();
        }
        context.globalAlpha = .7;
        context.beginPath(); context.moveTo(13,107); context.quadraticCurveTo(62,114,114,106); context.stroke();
    });
}

function forest(palette) {
    return drawing(128, context => {
        context.lineJoin = "round"; context.lineWidth = 1.2;
        context.fillStyle = palette.shadow; context.globalAlpha = .12;
        context.beginPath(); context.ellipse(64,105,53,9,0,0,Math.PI*2); context.fill(); context.globalAlpha = 1;
        for (const [x,y,size] of [[27,56,29],[87,54,31],[49,30,37],[103,74,24],[62,65,34]]) {
            path(context, [[x,y],[x-size*.43,y+size*.55],[x-size*.2,y+size*.5],[x-size*.6,y+size],[x-3,y+size],[x-3,y+size+10],[x+3,y+size+10],[x+3,y+size],[x+size*.6,y+size],[x+size*.2,y+size*.5],[x+size*.43,y+size*.55]], palette.vegetation, palette.border);
            context.strokeStyle = palette.paper; context.globalAlpha = .25;
            context.beginPath(); context.moveTo(x-2,y+size*.2); context.lineTo(x-2,y+size*.85); context.stroke(); context.globalAlpha = 1;
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

function illustrationData() {
    const points = [];
    const chain = (kind, coordinates) => coordinates.forEach(coordinate => points.push({type: "Feature", properties: {kind}, geometry: {type: "Point", coordinates: coordinate}}));
    chain("mountain", [[-124,58],[-119,52],[-114,46],[-109,39],[-104,31],[-74,7],[-77,-3],[-75,-12],[-70,-22],[-69,-33],[-72,-44],[8,46],[13,47],[22,46],[-5,31],[37,10],[39,-3],[43,-18],[45,42],[68,37],[76,34],[83,29],[91,29],[99,34],[105,39],[118,48],[95,53],[137,36],[145,-6],[171,-43]]);
    chain("forest", [[-131,58],[-102,57],[-87,54],[-69,51],[-63,-3],[-55,-6],[-70,-8],[-58,-15],[18,0],[24,-4],[31,1],[20,62],[31,63],[57,60],[76,61],[106,59],[121,57],[102,16],[114,1],[132,-4],[148,-22]]);
    chain("ship", [[-36,27],[-27,-24],[68,-24],[156,18],[-143,-27]]);
    return {type: "FeatureCollection", features: points};
}

function chartData() {
    const features = [];
    for (let longitude = -180; longitude <= 180; longitude += 30) features.push({type: "Feature", properties: {kind: "grid"}, geometry: {type: "LineString", coordinates: [[longitude,-80],[longitude,80]]}});
    for (let latitude = -60; latitude <= 60; latitude += 20) features.push({type: "Feature", properties: {kind: "grid"}, geometry: {type: "LineString", coordinates: Array.from({length:37},(_,index) => [-180+index*10,latitude])}});
    for (const coordinates of [[[-70,31],[-59,34],[-46,35],[-33,33],[-20,30],[-8,30]],[[-25,-8],[-10,-17],[10,-27],[35,-34],[60,-32],[80,-23],[96,-12]],[[145,15],[160,21],[175,23]]]) features.push({type: "Feature", properties: {kind:"route"}, geometry: {type:"LineString", coordinates}});
    return {type:"FeatureCollection",features};
}

export function prepareAdventure(controller, addLayer) {
    const {map} = controller;
    controller.adventurePaintKey = null;
    controller.adventureTopology ||= topology(controller.geometry);
    const source = (name, data) => { if (!map.getSource(PREFIX+name)) map.addSource(PREFIX+name,{type:"geojson",data}); };
    source("coast",controller.adventureTopology.coast);
    source("illustrations",illustrationData());
    source("chart",chartData());
    source("oceans",{type:"FeatureCollection",features:[[-143,29,"NORTH PACIFIC"],[-128,-30,"SOUTH PACIFIC"],[-36,9,"ATLANTIC OCEAN"],[80,-36,"INDIAN OCEAN"]].map(([x,y,name]) => ({type:"Feature",properties:{name},geometry:{type:"Point",coordinates:[x,y]}}))});
    const layer = (name,definition,before = FILL_LAYER) => addLayer(controller,{...definition,id:PREFIX+name,layout:{visibility:"none",...definition.layout}},before);
    // All sea detail and coast strokes sit beneath opaque country paint.
    layer("waves",{type:"background",paint:{"background-opacity":1}});
    layer("grid",{type:"line",source:PREFIX+"chart",filter:["==",["get","kind"],"grid"],paint:{"line-width":.65,"line-dasharray":[2,7],"line-opacity":["interpolate",["linear"],["zoom"],1,.13,4,.07,6,0]}});
    layer("routes",{type:"line",source:PREFIX+"chart",filter:["==",["get","kind"],"route"],layout:{"line-cap":"round","line-join":"round"},paint:{"line-width":1.1,"line-dasharray":[3,5],"line-opacity":["interpolate",["linear"],["zoom"],1,.3,3,.2,5,0]}});
    layer("coast-halo",{type:"line",source:PREFIX+"coast",layout:{"line-cap":"round","line-join":"round"},paint:{"line-width":["interpolate",["linear"],["zoom"],1,9,5,17],"line-opacity":.18,"line-blur":2}});
    layer("coast-etch",{type:"line",source:PREFIX+"coast",layout:{"line-cap":"round","line-join":"round"},paint:{"line-width":1,"line-gap-width":["interpolate",["linear"],["zoom"],1,8,5,14],"line-opacity":.3}});
    layer("paper",{type:"fill",source:COUNTRY_SOURCE,paint:{"fill-opacity":1}},OUTLINE_LAYER);
    layer("illustrations",{type:"symbol",source:PREFIX+"illustrations",minzoom:1.2,maxzoom:6,layout:{"icon-size":["interpolate",["linear"],["zoom"],1,.38,3,.6,5,.75],"icon-padding":8,"icon-anchor":"center"},paint:{"icon-opacity":["interpolate",["linear"],["zoom"],1,.75,3,.72,4,.4,6,0]}},LABEL_LAYER);
    layer("ocean-names",{type:"symbol",source:PREFIX+"oceans",maxzoom:5,layout:{"text-field":["get","name"],"text-font":["Noto Sans Regular"],"text-size":["interpolate",["linear"],["zoom"],1,11,3,16],"text-letter-spacing":.22,"text-max-width":20},paint:{"text-opacity":["interpolate",["linear"],["zoom"],1,.65,3,.6,5,0]}},LABEL_LAYER);
}

export function updateAdventure(controller, active, palette = adventurePalette()) {
    const {map} = controller;
    controller.page.dataset.mapType = controller.preferences.mapType;
    controller.container.setAttribute("aria-label", active ? "Interactive adventure world map" : "Interactive world map");
    for (const name of ["waves","grid","routes","coast-halo","coast-etch","paper","illustrations","ocean-names"]) {
        const id = PREFIX+name;
        if (!map.getLayer(id)) continue;
        const visible = active && (name !== "ocean-names" || controller.preferences.countryNames);
        if (map.getLayoutProperty(id,"visibility") !== (visible ? "visible" : "none")) map.setLayoutProperty(id,"visibility",visible ? "visible" : "none");
    }
    if (!active) return;
    if (controller.adventurePaintKey !== palette.name || !map.hasImage(PREFIX+"paper-"+palette.name)) {
        controller.adventurePaintKey = palette.name;
        for (const [name, painter] of Object.entries({paper,waves,mountain,forest,ship})) {
            const id = PREFIX+name+"-"+palette.name;
            if (!map.hasImage(id)) map.addImage(id,painter(palette),{pixelRatio:2});
        }
        map.setPaintProperty(PREFIX+"waves","background-pattern",PREFIX+"waves-"+palette.name);
        map.setPaintProperty(PREFIX+"paper","fill-pattern",PREFIX+"paper-"+palette.name);
        map.setLayoutProperty(PREFIX+"illustrations","icon-image",["concat",PREFIX,["get","kind"],"-"+palette.name]);
        for (const name of ["grid","routes","coast-halo","coast-etch"]) map.setPaintProperty(PREFIX+name,"line-color",name === "coast-halo" ? palette.shadow : palette.ink);
        map.setPaintProperty(PREFIX+"ocean-names","text-color",palette.ink);
        map.setPaintProperty(PREFIX+"ocean-names","text-halo-color",palette.sea);
        map.setPaintProperty(PREFIX+"ocean-names","text-halo-width",1);
    }
    const canvas = controller.page.querySelector("[data-adventure-compass]");
    const key = `${palette.name}:${map.getBearing()}`;
    if (canvas.dataset.paintKey !== key) { compass(canvas,palette,map.getBearing()); canvas.dataset.paintKey = key; }
}
