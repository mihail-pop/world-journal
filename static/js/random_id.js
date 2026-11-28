export function randomId() {
    // LAN installs can use HTTP, where randomUUID is unavailable.
    return crypto.randomUUID?.() ?? crypto.getRandomValues(new Uint32Array(4)).join("-");
}
