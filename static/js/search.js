export function initializePlaceSearch() {
    const overlay = document.querySelector("#place-search-overlay");
    const openButton = document.querySelector("[data-search-open]");
    if (!overlay || !openButton) return;
    const input = overlay.querySelector("#place-search-input");
    const results = overlay.querySelector("#place-search-results");
    const status = overlay.querySelector("[data-search-status]");
    const select = overlay.querySelector(".place-search-select");
    const toggle = overlay.querySelector("#place-search-type-toggle");
    const options = overlay.querySelector("#place-search-types");
    const types = [...options.querySelectorAll("[data-search-type]")];
    let selectedType = "all";
    let revision = 0;
    let request = null;
    let timer = null;
    let returnFocus = null;
    let previousOverflow = "";
    let inertElements = [];

    function cancelSearch() {
        revision++;
        request?.abort();
        request = null;
        clearTimeout(timer);
        results.removeAttribute("aria-busy");
    }

    function setOptionsOpen(open) {
        options.hidden = !open;
        select.classList.toggle("is-open", open);
        toggle.setAttribute("aria-expanded", String(open));
    }

    function close({restoreFocus = true} = {}) {
        if (overlay.hidden) return;
        cancelSearch();
        setOptionsOpen(false);
        overlay.hidden = true;
        document.body.style.overflow = previousOverflow;
        for (const [element, wasInert] of inertElements) element.inert = wasInert;
        inertElements = [];
        if (restoreFocus && returnFocus?.isConnected) returnFocus.focus({preventScroll: true});
    }

    openButton.addEventListener("click", () => {
        if (!overlay.hidden) return;
        returnFocus = openButton;
        previousOverflow = document.body.style.overflow;
        inertElements = [...document.querySelectorAll(".app-header, #app-content, #persistent-player")].map(element => [element, element.inert]);
        for (const [element] of inertElements) element.inert = true;
        document.body.style.overflow = "hidden";
        input.value = "";
        results.replaceChildren();
        status.textContent = "";
        setOptionsOpen(false);
        overlay.hidden = false;
        input.focus({preventScroll: true});
    });

    function showMessage(message) {
        const paragraph = document.createElement("p");
        paragraph.className = "place-search-message";
        paragraph.textContent = message;
        results.replaceChildren(paragraph);
        status.textContent = message;
    }

    async function search() {
        cancelSearch();
        const query = input.value.trim();
        if (!query || overlay.hidden) { results.replaceChildren(); status.textContent = ""; return; }
        const currentRevision = revision;
        const controller = new AbortController();
        request = controller;
        const url = new URL(overlay.dataset.searchUrl, location.origin);
        url.searchParams.set("q", query);
        url.searchParams.set("type", selectedType);
        results.setAttribute("aria-busy", "true");
        try {
            const response = await fetch(url, {signal: controller.signal, headers: {Accept: "application/json"}});
            if (!response.ok) throw new Error("Place search failed");
            const data = await response.json();
            if (revision !== currentRevision || overlay.hidden) return;
            if (!data.results.length) { showMessage("No matching places. Smaller towns may not be included."); return; }
            const list = document.createElement("ul");
            list.className = "place-search-list";
            for (const place of data.results) {
                const row = document.createElement("li");
                const link = document.createElement("a");
                link.className = "place-search-result";
                link.href = place.url;
                link.dataset.placeResult = place.id;
                const flag = document.createElement("span");
                flag.className = "place-search-flag";
                flag.setAttribute("aria-hidden", "true");
                const fallback = document.createElement("span");
                fallback.textContent = place.flag;
                flag.append(fallback);
                if (place.flag) {
                    const image = document.createElement("img");
                    image.alt = "";
                    image.referrerPolicy = "no-referrer";
                    image.hidden = true;
                    image.onload = () => { image.hidden = false; fallback.hidden = true; };
                    image.onerror = () => { image.hidden = true; fallback.hidden = false; };
                    image.src = `https://flagcdn.com/${place.country.toLowerCase()}.svg`;
                    flag.append(image);
                }
                const description = document.createElement("span");
                description.className = "place-search-description";
                const name = document.createElement("span");
                name.className = "place-search-name";
                name.textContent = place.label;
                const detail = document.createElement("span");
                detail.className = "place-search-detail";
                const kind = {country: "Country", capital: "Capital", city: "City"}[place.kind];
                detail.textContent = place.region ? `${kind} · ${place.region}` : kind;
                description.append(name, detail);
                link.append(flag, description);
                row.append(link);
                list.append(row);
            }
            results.replaceChildren(list);
            window.htmx?.process(results);
            status.textContent = `${data.results.length} results`;
        } catch (error) {
            if (error.name !== "AbortError" && revision === currentRevision && !overlay.hidden) {
                showMessage("Search is unavailable. Press Enter to try again.");
            }
        } finally {
            if (revision === currentRevision) {
                request = null;
                results.removeAttribute("aria-busy");
            }
        }
    }

    function scheduleSearch() {
        cancelSearch();
        results.replaceChildren();
        status.textContent = "";
        if (input.value.trim()) timer = setTimeout(search, 180);
    }

    input.addEventListener("input", event => { if (!event.isComposing) scheduleSearch(); });
    input.addEventListener("compositionend", scheduleSearch);
    overlay.querySelector("form").addEventListener("submit", event => { event.preventDefault(); search(); });
    select.addEventListener("mouseenter", () => { if (matchMedia("(hover: hover)").matches) setOptionsOpen(true); });
    select.addEventListener("mouseleave", () => { if (matchMedia("(hover: hover)").matches && !options.contains(document.activeElement)) setOptionsOpen(false); });
    select.addEventListener("focusout", event => { if (!select.contains(event.relatedTarget)) setOptionsOpen(false); });
    toggle.addEventListener("click", event => {
        setOptionsOpen(event.detail > 0 && matchMedia("(hover: hover)").matches ? true : options.hidden);
    });
    for (const button of types) button.addEventListener("click", () => {
        selectedType = button.dataset.searchType;
        overlay.querySelector("[data-search-type-label]").textContent = button.textContent;
        for (const option of types) option.setAttribute("aria-pressed", String(option === button));
        setOptionsOpen(false);
        input.focus();
        search();
    });
    overlay.addEventListener("click", event => {
        if (!select.contains(event.target)) setOptionsOpen(false);
        if (event.target === overlay) close();
        const link = event.target.closest("[data-place-result]");
        if (link && event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
            document.dispatchEvent(new CustomEvent("world-journal:place-search-navigate"));
            close({restoreFocus: false});
        }
    });
    window.addEventListener("popstate", () => close({restoreFocus: false}));
    document.addEventListener("keydown", event => {
        if (overlay.hidden) return;
        if (event.key === "Escape") {
            event.preventDefault();
            event.stopImmediatePropagation();
            if (!options.hidden) { setOptionsOpen(false); toggle.focus(); }
            else close();
            return;
        }
        if (event.key === "Tab") {
            const focusable = [...overlay.querySelectorAll("input, button, a[href]")].filter(element => element.getClientRects().length);
            const first = focusable[0];
            const last = focusable.at(-1);
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
        if (["ArrowDown", "ArrowUp"].includes(event.key)) {
            if (select.contains(document.activeElement)) {
                event.preventDefault();
                setOptionsOpen(true);
                const current = types.indexOf(document.activeElement);
                types[(current + (event.key === "ArrowDown" ? 1 : -1) + types.length) % types.length].focus();
            } else {
                const links = [...results.querySelectorAll("[data-place-result]")];
                const current = links.indexOf(document.activeElement);
                if (links.length && (current >= 0 || document.activeElement === input)) {
                    event.preventDefault();
                    const next = current + (event.key === "ArrowDown" ? 1 : -1);
                    (next < 0 ? input : links[Math.min(next, links.length - 1)]).focus();
                }
            }
        }
    }, true);
}
