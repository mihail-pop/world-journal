export function recordCountrySelection(page, code) {
    const token = document.querySelector('meta[name="csrf-token"]')?.content;
    const route = page.dataset.countrySelectionUrlTemplate;
    if (!token || !route) return;
    // Selection and navigation do not depend on the counter request.
    void fetch(route.replace("COUNTRY_CODE", encodeURIComponent(code)), {
        method: "POST", headers: {"X-CSRFToken": token}, keepalive: true,
    }).catch(() => {});
}
