// Composite the existing translucent overlays before drawing. The renderer
// then needs one country fill instead of four full-geometry fill passes.
function rgb(hex) {
    return [1, 3, 5].map(offset => Number.parseInt(hex.slice(offset, offset + 2), 16));
}

function overlay(background, foreground, opacity) {
    const alpha = opacity + background.alpha * (1 - opacity);
    return {
        alpha,
        rgb: foreground.map((channel, index) => (
            channel * opacity + background.rgb[index] * background.alpha * (1 - opacity)
        ) / alpha),
    };
}

function color(value) {
    return `rgba(${value.rgb.map(Math.round).join(",")},${value.alpha})`;
}

export function countryFillColors(theme, presetColor = null) {
    let normal = {rgb: rgb(theme.fill), alpha: theme.opacity};
    if (presetColor) normal = overlay(normal, rgb(presetColor), .65);
    const accent = rgb(theme.accent);
    const hovered = overlay(normal, accent, .32);
    return {
        fillNormal: color(normal),
        fillHovered: color(hovered),
        fillSelected: color(overlay(normal, accent, .26)),
        fillHoveredSelected: color(overlay(hovered, accent, .26)),
    };
}

export function countryFillExpression() {
    // This expression stays fixed even when terrain/theme/preset changes.
    // Only feature state changes, avoiding asynchronous tile-layout rebuilds.
    const value = key => ["to-color", ["coalesce", ["feature-state", key], "rgba(0,0,0,0)"]];
    const hovered = ["boolean", ["feature-state", "hover"], false];
    const selected = ["boolean", ["feature-state", "selected"], false];
    return ["case",
        selected, ["case", hovered, value("fillHoveredSelected"), value("fillSelected")],
        hovered, value("fillHovered"), value("fillNormal"),
    ];
}
