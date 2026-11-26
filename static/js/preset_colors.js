export function presetColorValue(value) {
    const text = value.trim().toLowerCase();
    if (!text || /^#[0-9a-f]{6}$/.test(text)) return text;
    if (/^#[0-9a-f]{3}$/.test(text)) return `#${[...text.slice(1)].map(char => char + char).join("")}`;
    const rgb = text.match(/^(?:rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)|(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3}))$/);
    if (!rgb) return null;
    const channels = rgb.slice(1).filter(channel => channel !== undefined).map(Number);
    return channels.every(channel => channel <= 255)
        ? `#${channels.map(channel => channel.toString(16).padStart(2, "0")).join("")}` : null;
}
