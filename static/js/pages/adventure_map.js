// Original, deterministic chart artwork. Geography always comes from the
// application's unchanged country polygons; these illustrations are decorative.
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
    const theme = document.documentElement.dataset.theme;
    return {name: theme in palettes ? theme : "dark", ...(palettes[theme] || palettes.dark)};
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

function mountain(palette, snowy = false) {
    return drawing(128, context => {
        const stone = snowy ? "#a8b7af" : palette.land[1];
        const snow = snowy ? "#f5efd8" : palette.paper;
        context.lineJoin = "round"; context.lineCap = "round"; context.lineWidth = 1.5;
        context.fillStyle = palette.shadow; context.globalAlpha = .12;
        context.beginPath(); context.ellipse(64, 103, 55, 8, 0, 0, Math.PI * 2); context.fill();
        context.globalAlpha = 1;
        path(context, [[7,100],[35,52],[67,103]], stone, palette.border);
        path(context, [[40,103],[86,39],[123,102]], snowy ? snow : palette.land[6], palette.border);
        path(context, [[21,105],[62,19],[101,105]], snow, palette.border);
        path(context, [[62,19],[62,105],[101,105]], stone, null);
        path(context, snowy ? [[41,64],[62,19],[83,64],[70,53],[64,64],[57,54],[49,63]] : [[48,48],[62,19],[76,48],[66,42],[61,50],[56,42]], snow, palette.border);
        if (snowy) {
            path(context, [[23,74],[35,52],[46,73],[36,69],[32,76]], snow, palette.border);
            path(context, [[73,58],[86,39],[98,59],[88,53],[83,61]], snow, palette.border);
        }
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

function desert(palette) {
    return drawing(128, context => {
        context.lineJoin = "round"; context.lineCap = "round"; context.lineWidth = 1.5;
        context.fillStyle = palette.shadow; context.globalAlpha = .1;
        context.beginPath(); context.ellipse(64,104,55,8,0,0,Math.PI*2); context.fill(); context.globalAlpha = 1;
        context.fillStyle = palette.land[4]; context.strokeStyle = palette.border;
        context.beginPath(); context.moveTo(9,93); context.bezierCurveTo(26,88,43,45,73,51);
        context.bezierCurveTo(91,59,102,75,120,83); context.lineTo(115,103); context.lineTo(15,106); context.closePath(); context.fill(); context.stroke();
        context.fillStyle = palette.land[1];
        context.beginPath(); context.moveTo(9,101); context.bezierCurveTo(42,97,65,70,88,76);
        context.bezierCurveTo(99,81,111,96,121,104); context.quadraticCurveTo(60,117,9,101); context.fill(); context.stroke();
        context.strokeStyle = palette.paper; context.lineWidth = 2; context.globalAlpha = .7;
        context.beginPath(); context.moveTo(20,93); context.bezierCurveTo(38,82,48,57,72,53); context.stroke();
        context.beginPath(); context.moveTo(30,100); context.quadraticCurveTo(61,91,88,78); context.stroke();
        context.strokeStyle = palette.border; context.lineWidth = .8; context.globalAlpha = .3;
        for (let index = 0; index < 6; index++) {
            context.beginPath(); context.moveTo(78+index*4,59+index*4); context.quadraticCurveTo(82+index*4,77+index*3,95+index*3,85+index*3); context.stroke();
        }
    });
}

function grove(palette) {
    return drawing(128, context => {
        context.lineJoin = "round"; context.lineCap = "round"; context.lineWidth = 1.4;
        context.fillStyle = palette.shadow; context.globalAlpha = .12;
        context.beginPath(); context.ellipse(65,106,47,7,0,0,Math.PI*2); context.fill(); context.globalAlpha = 1;
        for (const [x,y,height] of [[83,48,52],[44,32,73]]) {
            context.strokeStyle = palette.border; context.fillStyle = palette.land[1];
            context.beginPath(); context.moveTo(x-5,y+height); context.quadraticCurveTo(x+8,y+height*.5,x,y);
            context.quadraticCurveTo(x+2,y+height*.5,x+3,y+height); context.closePath(); context.fill(); context.stroke();
            for (const [dx,dy] of [[-32,-8],[-33,14],[-19,26],[28,-13],[36,9],[22,27]]) {
                context.fillStyle = palette.vegetation;
                context.beginPath(); context.moveTo(x,y); context.quadraticCurveTo(x+dx*.35,y+dy-17,x+dx,y+dy);
                context.quadraticCurveTo(x+dx*.55,y+dy-4,x,y+3); context.closePath(); context.fill(); context.stroke();
                context.strokeStyle = palette.paper; context.globalAlpha = .25;
                context.beginPath(); context.moveTo(x,y); context.quadraticCurveTo(x+dx*.55,y+dy-7,x+dx,y+dy); context.stroke();
                context.globalAlpha = 1; context.strokeStyle = palette.border;
            }
            context.globalAlpha = .45;
            for (let offset = 15; offset < height; offset += 10) {
                context.beginPath(); context.moveTo(x-1,y+offset); context.lineTo(x+4,y+offset+2); context.stroke();
            }
            context.globalAlpha = 1;
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

function dragon(palette) {
    return drawing(128, context => {
        context.lineJoin = "round"; context.lineCap = "round"; context.lineWidth = 1.5;
        context.strokeStyle = palette.border;
        context.fillStyle = palette.land[2];
        context.beginPath(); context.moveTo(63,73); context.lineTo(35,11); context.quadraticCurveTo(38,38,28,38);
        context.lineTo(12,27); context.quadraticCurveTo(23,49,17,58); context.lineTo(7,58);
        context.quadraticCurveTo(24,73,35,86); context.closePath(); context.fill(); context.stroke();
        context.fillStyle = palette.land[1];
        context.beginPath(); context.moveTo(60,73); context.lineTo(88,18); context.quadraticCurveTo(79,44,86,51);
        context.lineTo(105,40); context.quadraticCurveTo(97,61,104,72); context.quadraticCurveTo(84,68,74,83); context.closePath(); context.fill(); context.stroke();
        context.globalAlpha = .45;
        for (const tip of [[35,15],[16,31],[89,22],[101,44]]) {
            context.beginPath(); context.moveTo(61,74); context.lineTo(...tip); context.stroke();
        }
        context.globalAlpha = 1; context.fillStyle = palette.vegetation;
        context.beginPath(); context.moveTo(72,72); context.quadraticCurveTo(87,64,87,53);
        context.quadraticCurveTo(86,44,95,43); context.lineTo(107,48); context.lineTo(115,54);
        context.lineTo(103,58); context.quadraticCurveTo(102,74,84,88);
        context.bezierCurveTo(60,105,34,87,24,102); context.quadraticCurveTo(32,116,50,107);
        context.quadraticCurveTo(38,123,22,111); context.quadraticCurveTo(11,98,30,93);
        context.quadraticCurveTo(57,91,72,72); context.closePath(); context.fill(); context.stroke();
        path(context, [[89,45],[90,34],[97,43]], palette.paper, palette.border);
        context.fillStyle = palette.paper; context.beginPath(); context.arc(98,49,2.2,0,Math.PI*2); context.fill();
        context.fillStyle = palette.border; context.beginPath(); context.arc(99,49,1,0,Math.PI*2); context.fill();
        context.beginPath(); context.moveTo(83,83); context.lineTo(92,94); context.lineTo(104,96);
        context.moveTo(91,93); context.lineTo(99,91); context.moveTo(64,92); context.lineTo(66,103); context.lineTo(78,108); context.stroke();
        context.strokeStyle = palette.paper; context.globalAlpha = .3;
        context.beginPath(); context.moveTo(41,97); context.quadraticCurveTo(76,90,96,61); context.stroke();
    });
}

function unicorn(palette) {
    return drawing(128, context => {
        context.lineJoin = "round"; context.lineCap = "round"; context.lineWidth = 1.5;
        context.fillStyle = palette.shadow; context.globalAlpha = .12;
        context.beginPath(); context.ellipse(65,108,47,7,0,0,Math.PI*2); context.fill(); context.globalAlpha = 1;
        context.strokeStyle = palette.border; context.fillStyle = palette.paper;
        context.beginPath(); context.moveTo(29,65); context.bezierCurveTo(43,53,64,62,74,53);
        context.lineTo(83,34); context.lineTo(94,30); context.lineTo(111,42); context.lineTo(106,51);
        context.lineTo(93,48); context.lineTo(87,72); context.lineTo(91,103); context.lineTo(81,104);
        context.lineTo(77,81); context.lineTo(68,82); context.lineTo(58,102); context.lineTo(47,104);
        context.lineTo(55,82); context.lineTo(39,83); context.lineTo(34,105); context.lineTo(23,105);
        context.lineTo(28,79); context.quadraticCurveTo(20,72,29,65); context.closePath(); context.fill(); context.stroke();
        path(context, [[96,33],[103,13],[104,38]], palette.land[4], palette.border);
        path(context, [[87,34],[84,23],[91,30]], palette.paper, palette.border);
        context.fillStyle = palette.land[2];
        context.beginPath(); context.moveTo(88,33); context.quadraticCurveTo(70,39,67,65);
        context.quadraticCurveTo(81,56,87,42); context.closePath(); context.fill(); context.stroke();
        context.beginPath(); context.moveTo(28,68); context.bezierCurveTo(9,68,23,86,10,92);
        context.bezierCurveTo(33,86,24,80,31,75); context.closePath(); context.fill(); context.stroke();
        context.fillStyle = palette.border; context.beginPath(); context.arc(97,40,1.6,0,Math.PI*2); context.fill();
        for (const [x,y] of [[24,105],[48,104],[81,104]]) { context.beginPath(); context.moveTo(x,y); context.lineTo(x+9,y); context.stroke(); }
        context.globalAlpha = .35;
        for (let offset = 0; offset < 4; offset++) { context.beginPath(); context.moveTo(36+offset*5,71); context.lineTo(40+offset*5,77); context.stroke(); }
    });
}

function golem(palette) {
    return drawing(128, context => {
        context.lineJoin = "round"; context.lineCap = "round"; context.lineWidth = 1.5;
        context.fillStyle = palette.shadow; context.globalAlpha = .12;
        context.beginPath(); context.ellipse(65,110,44,6,0,0,Math.PI*2); context.fill(); context.globalAlpha = 1;
        for (const points of [
            [[24,56],[42,50],[44,73],[33,84],[20,76]], [[83,51],[101,57],[108,77],[93,86],[82,73]],
            [[43,84],[61,88],[59,109],[38,109],[36,101]], [[67,87],[83,83],[91,104],[85,109],[66,109]],
            [[41,47],[64,41],[85,49],[87,79],[69,94],[42,80]], [[48,23],[72,20],[83,33],[78,52],[51,53],[43,37]],
        ]) path(context, points, palette.land[5], palette.border);
        context.strokeStyle = palette.border;
        for (const points of [[[47,61],[58,66],[54,81]],[[73,53],[67,70],[83,77]],[[53,24],[62,33],[59,44]]]) {
            context.beginPath(); points.forEach(([x,y],index) => index ? context.lineTo(x,y) : context.moveTo(x,y)); context.stroke();
        }
        context.fillStyle = palette.border;
        for (const x of [56,70]) { context.beginPath(); context.ellipse(x,37,3.5,2.5,0,0,Math.PI*2); context.fill(); }
        context.beginPath(); context.moveTo(58,46); context.lineTo(69,46); context.stroke();
        path(context, [[42,51],[35,45],[44,40],[51,43]], palette.vegetation, palette.border);
        path(context, [[70,24],[72,14],[79,10],[81,21]], palette.vegetation, palette.border);
        context.strokeStyle = palette.paper; context.globalAlpha = .35;
        context.beginPath(); context.moveTo(46,59); context.lineTo(45,75); context.moveTo(50,29); context.lineTo(48,39); context.stroke();
    });
}

function spiritFox(palette) {
    return drawing(128, context => {
        context.lineJoin = "round"; context.lineCap = "round"; context.lineWidth = 1.5;
        context.fillStyle = palette.shadow; context.globalAlpha = .12;
        context.beginPath(); context.ellipse(66,107,48,6,0,0,Math.PI*2); context.fill(); context.globalAlpha = 1;
        context.fillStyle = palette.paper; context.strokeStyle = palette.border;
        context.beginPath(); context.moveTo(57,78); context.bezierCurveTo(22,80,14,49,18,30);
        context.bezierCurveTo(36,38,59,51,59,77); context.closePath(); context.fill(); context.stroke();
        context.beginPath(); context.moveTo(38,78); context.quadraticCurveTo(65,66,80,80);
        context.lineTo(85,103); context.lineTo(73,104); context.lineTo(67,88); context.lineTo(57,90);
        context.lineTo(51,104); context.lineTo(36,104); context.quadraticCurveTo(28,90,38,78); context.closePath(); context.fill(); context.stroke();
        path(context, [[68,72],[70,33],[84,49],[95,31],[107,61],[104,74],[86,87]], palette.paper, palette.border);
        path(context, [[73,41],[80,52],[73,56]], palette.land[2], null);
        path(context, [[95,39],[101,56],[94,52]], palette.land[2], null);
        context.strokeStyle = palette.vegetation; context.globalAlpha = .65;
        context.beginPath(); context.moveTo(39,89); context.quadraticCurveTo(36,65,26,53); context.stroke();
        context.globalAlpha = 1; context.strokeStyle = palette.border;
        context.beginPath(); context.moveTo(77,66); context.lineTo(82,68); context.moveTo(93,68); context.lineTo(98,66); context.stroke();
        path(context, [[85,75],[89,75],[87,78]], palette.border, null);
        context.strokeStyle = palette.paper; context.globalAlpha = .5;
        context.beginPath(); context.moveTo(41,53); context.lineTo(48,65); context.stroke();
    });
}

function volcano(palette) {
    return drawing(128, context => {
        context.lineJoin = "round"; context.lineCap = "round"; context.lineWidth = 1.5;
        context.fillStyle = palette.shadow; context.globalAlpha = .12;
        context.beginPath(); context.ellipse(64,107,53,7,0,0,Math.PI*2); context.fill(); context.globalAlpha = 1;
        // Broad cone, open crater and a narrow lava seam echo the mountain art.
        path(context, [[10,105],[40,62],[49,47],[76,47],[87,69],[119,106]], palette.land[1], palette.border);
        path(context, [[66,51],[76,47],[87,69],[119,106],[68,107]], palette.land[2], null);
        context.fillStyle = palette.border;
        context.beginPath(); context.ellipse(63,48,14,4,0,0,Math.PI*2); context.fill();
        context.strokeStyle = palette.accent; context.lineWidth = 3;
        context.beginPath(); context.moveTo(59,50); context.quadraticCurveTo(54,62,64,72);
        context.quadraticCurveTo(68,81,60,88); context.lineTo(63,103); context.stroke();
        context.fillStyle = palette.paper; context.strokeStyle = palette.border; context.lineWidth = 1.2;
        context.beginPath(); context.moveTo(58,43); context.bezierCurveTo(42,34,54,31,50,24);
        context.bezierCurveTo(38,20,49,10,58,15); context.bezierCurveTo(63,4,77,11,75,18);
        context.bezierCurveTo(94,16,93,31,79,32); context.quadraticCurveTo(68,33,67,43);
        context.closePath(); context.fill(); context.stroke();
        context.globalAlpha = .35;
        for (let y = 69; y < 102; y += 7) {
            context.beginPath(); context.moveTo(79,y); context.lineTo(84+(y-69)*.55,y+5); context.stroke();
        }
        context.strokeStyle = palette.paper; context.globalAlpha = .6;
        context.beginPath(); context.moveTo(17,102); context.lineTo(43,65); context.stroke();
    });
}

function tornado(palette) {
    return drawing(128, context => {
        context.lineJoin = "round"; context.lineCap = "round"; context.lineWidth = 1.4;
        context.fillStyle = palette.shadow; context.globalAlpha = .12;
        context.beginPath(); context.ellipse(69,111,31,5,0,0,Math.PI*2); context.fill(); context.globalAlpha = 1;
        context.fillStyle = palette.land[5]; context.strokeStyle = palette.border;
        context.beginPath(); context.moveTo(25,36); context.bezierCurveTo(44,52,53,77,66,108);
        context.quadraticCurveTo(74,99,77,88); context.bezierCurveTo(72,67,95,52,104,36);
        context.closePath(); context.fill(); context.stroke();
        context.fillStyle = palette.paper;
        context.beginPath(); context.moveTo(19,34); context.bezierCurveTo(6,21,25,15,34,20);
        context.bezierCurveTo(35,7,56,7,61,17); context.bezierCurveTo(73,6,95,13,91,24);
        context.bezierCurveTo(113,14,124,30,111,37); context.quadraticCurveTo(67,45,19,34);
        context.closePath(); context.fill(); context.stroke();
        for (const [y,left,right] of [[49,35,95],[61,43,85],[73,51,78],[85,57,75],[97,62,71]]) {
            context.strokeStyle = palette.border; context.globalAlpha = .7;
            context.beginPath(); context.moveTo(left,y); context.quadraticCurveTo((left+right)/2,y+8,right,y+1); context.stroke();
            context.strokeStyle = palette.paper; context.globalAlpha = .55;
            context.beginPath(); context.moveTo(left+3,y+2); context.quadraticCurveTo((left+right)/2,y+6,right-3,y+3); context.stroke();
        }
        context.globalAlpha = .6; context.strokeStyle = palette.ink;
        context.beginPath(); context.moveTo(42,96); context.quadraticCurveTo(23,101,39,106);
        context.moveTo(89,91); context.quadraticCurveTo(103,99,88,104); context.stroke();
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
    chain("mountain", [[-109,39],[-104,31],[-74,7],[-77,-3],[-75,-12],[-70,-22],[22,46],[-5,31],[37,10],[47,-20],[68,37],[99,34],[105,39],[118,48],[145,-6]],"land");
    chain("snow-mountain", [[-150,63],[-124,58],[-119,52],[-114,46],[-72,-44],[8,46],[13,47],[8,61],[-44,65],[45,42],[76,34],[83,29],[91,29],[95,53],[171,-43]],"land");
    chain("forest", [[-131,58],[-102,57],[-87,54],[-69,51],[20,62],[31,63],[57,60],[76,61],[106,59],[121,57]],"land");
    chain("grove", [[-63,-3],[-55,-6],[-70,-8],[-58,-15],[18,0],[24,-4],[31,1],[102,16],[114,1],[132,-4],[146,-18]],"land");
    chain("desert", [[-8,23],[8,25],[20,23],[45,22],[15,-23],[-69,-24],[103,42],[124,-25]],"land");
    chain("ship", [[-36,27],[-27,-24],[68,-24],[156,18],[-143,-27]]);
    chain("sea-monster", [[-16,-16],[-158,47]],"sea");
    chain("dragon", [[110,31],[27,-27]],"land");
    chain("unicorn", [[10,50],[-108,51]],"land");
    chain("golem", [[-111,35],[96,46]],"land");
    chain("spirit-fox", [[28,67],[125,63]],"land");
    // Decorative volcanic belts, not an inventory or current eruption report.
    chain("volcano", [[-19,65],[-98.6,19],[-69,-33],[37.3,-3.1],[140,39],[110.4,-7.5],[159,56]],"land");
    chain("tornado", [[-98,38],[-63,-32]],"land");
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
    const waterArtwork = ["in",["get","kind"],["literal",["ship","sea-monster"]]];
    layer("illustrations",{type:"symbol",source:PREFIX+"illustrations",filter:waterArtwork,layout:illustrationLayout,paint:{"icon-opacity":1}},HOVER_OUTLINE_LAYER);
    layer("land-illustrations",{type:"symbol",source:PREFIX+"illustrations",minzoom:3.2,maxzoom:6.5,filter:["!",waterArtwork],layout:illustrationLayout,paint:{"icon-opacity":["interpolate",["linear"],["zoom"],3.2,0,3.8,1,5.3,1,6.5,0]}},HOVER_OUTLINE_LAYER);
    layer("ocean-names",{type:"symbol",source:PREFIX+"oceans",maxzoom:5,layout:{"text-field":["get","name"],"text-font":["Noto Sans Regular"],"text-size":["interpolate",["linear"],["zoom"],1,11,3,16],"text-letter-spacing":.22,"text-max-width":20},paint:{"text-opacity":["interpolate",["linear"],["zoom"],1,.65,3,.6,5,0]}},LABEL_LAYER);
}

export function updateAdventure(controller, active, palette = adventurePalette()) {
    const {map} = controller;
    controller.page.dataset.mapType = controller.preferences.mapType;
    controller.container.setAttribute("aria-label", active ? "Interactive adventure world map" : "Interactive world map");
    for (const name of ["waves","grid","routes","paper","illustrations","land-illustrations","ocean-names"]) {
        const id = PREFIX+name;
        if (!map.getLayer(id)) continue;
        const visible = active && (name !== "ocean-names" || controller.preferences.countryNames);
        if (map.getLayoutProperty(id,"visibility") !== (visible ? "visible" : "none")) map.setLayoutProperty(id,"visibility",visible ? "visible" : "none");
    }
    if (!active) { updateAdventureMarkers(controller,false,palette); return; }
    if (controller.adventurePaintKey !== palette.name || !map.hasImage(PREFIX+"paper-"+palette.name)) {
        controller.adventurePaintKey = palette.name;
        controller.adventureImages ||= new Map();
        for (const [name, painter] of Object.entries({paper,waves,mountain,forest,ship,desert,grove,volcano,tornado,"snow-mountain": palette => mountain(palette,true),"sea-monster":seaMonster,dragon,unicorn,golem,"spirit-fox":spiritFox,"favorite-heart":fantasyHeart})) {
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
        map.setLayoutProperty(PREFIX+"land-illustrations","icon-image",["concat",PREFIX,["get","kind"],"-"+palette.name]);
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
        // Clear the label's upper half and the heart's visible lower half,
        // leaving about two pixels of space. Keep one position at every zoom.
        // Offsets use unscaled icon pixels (icon-size is .9).
        const labelOffset = fontSize => ["case",
            [">=",["get","label_rows"],4],["literal",[0,-(4*fontSize*.6+6)/.9]],
            [">=",["get","label_rows"],3],["literal",[0,-(3*fontSize*.6+6)/.9]],
            [">=",["get","label_rows"],2],["literal",[0,-(2*fontSize*.6+6)/.9]],
            ["literal",[0,-(fontSize*.6+6)/.9]]];
        map.setLayoutProperty(favoriteLayer,"icon-anchor","center");
        map.setLayoutProperty(favoriteLayer,"icon-offset",labelOffset(active ? 16 : 14));
    }
}
