function fontFamilies() {
    return getComputedStyle(document.documentElement).getPropertyValue("--ui-font-family")
        .split(",")
        .map(family => family.trim().replace(/^["']|["']$/g, ""))
        .filter(Boolean);
}

export function mapFontStack(original = "Regular", families = fontFamilies()) {
    const description = JSON.stringify(original);
    const weight = description.match(/\b(?:extra bold|semibold|bold|medium|light|black)\b/i)?.[0] || "Regular";
    const style = description.match(/\b(?:italic|oblique)\b/i)?.[0];
    // MapLibre reads weight/style from the first family name. This unregistered
    // name supplies those hints; the following families are the actual UI fonts.
    return [`World Journal Map ${weight}${style ? ` ${style}` : ""}`, ...families];
}

function withLocalFont(layer, families) {
    if (layer.type !== "symbol" || layer.layout?.["text-field"] == null) return layer;
    return {...layer, layout: {...layer.layout, "text-font": mapFontStack(layer.layout["text-font"], families)}};
}

export function localMapStyle(_previousStyle, nextStyle) {
    const style = {...nextStyle};
    // Omitting glyphs enables MapLibre's built-in browser font rendering.
    delete style.glyphs;
    const families = fontFamilies();
    style.layers = style.layers.map(layer => withLocalFont(layer, families));
    return style;
}

export function updateMapFonts(controller) {
    const families = fontFamilies();
    const key = JSON.stringify(families);
    if (controller.mapFontKey === key) return;
    for (const layer of controller.map.getStyle().layers) {
        const updated = withLocalFont(layer, families);
        if (updated !== layer) controller.map.setLayoutProperty(layer.id, "text-font", updated.layout["text-font"]);
    }
    controller.mapFontKey = key;
}
