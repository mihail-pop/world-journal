import { FAVORITES_DISPLAY_MODES, readMapPreferences, writeMapPreferences } from "../map_preferences.js";

const EDGE = 12;
const BUTTON = 44;
const FAVORITE_ROW = 36;
const FAVORITE_ROWS = 10;
const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(value, maximum));
const normalize = value => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
const snap = value => Math.round(value * (window.devicePixelRatio || 1)) / (window.devicePixelRatio || 1);

export function initializeMapControls(controller, selectCountry) {
    const {page, toolbar, controlsToggle: toggle, controlsPanel: panel} = controller;
    const {signal} = controller.abortController;
    const workspace = page.querySelector(".map-workspace");
    const favorites = page.querySelector("[data-map-favorites-panel]");
    const list = page.querySelector("[data-map-favorites-list]");
    const zoom = page.querySelector(".map-zoom-controls");
    const favoritesToggle = panel.querySelector("[data-map-favorites-toggle]");
    const closeButton = panel.querySelector("[data-map-controls-close]");
    const menuBar = panel.querySelector(".map-menu-top");
    const search = favorites.querySelector("[data-map-favorites-search]");
    const searchToggle = search.querySelector("button");
    const query = search.querySelector("input");
    const legend = page.querySelector("[data-map-preset-legend]");
    const empty = document.createElement("p");
    let dragging = null, suppressClick = false, signature = "", frame = null;

    function scheduleLayout() {
        if (frame !== null) return;
        frame = requestAnimationFrame(() => { frame = null; layout(); });
    }

    function relativeRect(element, area) {
        const rect = element.getBoundingClientRect();
        return {left: rect.left - area.rect.left, right: rect.right - area.rect.left,
            top: rect.top - area.rect.top, bottom: rect.bottom - area.rect.top};
    }

    function freeIntervals(left, width, obstacles, area) {
        let gaps = [{top: area.top, bottom: area.bottom}];
        for (const obstacle of obstacles) {
            if (left >= obstacle.right + EDGE || left + width <= obstacle.left - EDGE) continue;
            gaps = gaps.flatMap(gap => {
                if (obstacle.bottom + EDGE <= gap.top || obstacle.top - EDGE >= gap.bottom) return [gap];
                return [{top: gap.top, bottom: Math.min(gap.bottom, obstacle.top - EDGE)},
                    {top: Math.max(gap.top, obstacle.bottom + EDGE), bottom: gap.bottom}].filter(part => part.bottom > part.top);
            });
        }
        return gaps;
    }

    function place(element, {left, width, height, minimum, bottom = false}, obstacles, area) {
        const candidates = [left, EDGE, area.right - width,
            ...obstacles.flatMap(rect => [rect.right + EDGE, rect.left - EDGE - width])]
            .map(x => clamp(x, EDGE, Math.max(EDGE, area.right - width)));
        let chosen;
        for (const x of new Set(candidates)) {
            const gaps = freeIntervals(x, width, obstacles, area);
            const fitting = bottom && gaps.filter(gap => gap.bottom - gap.top >= height);
            const gap = fitting?.length ? fitting.at(-1) : gaps.sort((a, b) => (b.bottom - b.top) - (a.bottom - a.top) || a.top - b.top)[0];
            if (!gap) continue;
            const space = gap.bottom - gap.top;
            if (!chosen || space > chosen.space) chosen = {x, gap, space};
            if (space >= minimum) { chosen = {x, gap, space}; break; }
        }
        if (!chosen) return null;
        const size = Math.min(height, chosen.space);
        const top = bottom ? chosen.gap.bottom - size : chosen.gap.top;
        element.style.left = `${snap(chosen.x)}px`;
        element.style.top = `${snap(top)}px`;
        element.style.right = element.style.bottom = "auto";
        element.style.maxHeight = `${size}px`;
        return {left: chosen.x, right: chosen.x + width, top, bottom: top + size};
    }

    function bounds() {
        const rect = workspace.getBoundingClientRect();
        const header = document.querySelector(".app-header")?.getBoundingClientRect();
        let right = rect.width - EDGE, bottom = rect.height - EDGE;
        const drawer = page.querySelector(".country-drawer:not([hidden])")?.getBoundingClientRect();
        if (drawer?.width) {
            if (drawer.width > rect.width * .8) bottom = Math.min(bottom, drawer.top - rect.top - EDGE);
            else right = Math.min(right, drawer.left - rect.left - EDGE);
        }
        const top = Math.ceil(Math.max(EDGE, (header?.bottom || 0) - rect.top + EDGE));
        return {rect, top, right: Math.max(BUTTON + EDGE, right), bottom: Math.max(top + BUTTON, bottom)};
    }

    function layoutPanel(area = bounds()) {
        if (panel.hidden) return;
        const x = parseFloat(toolbar.style.left) || EDGE;
        const y = parseFloat(toolbar.style.top) || area.top;
        const rightRoom = area.right - x, leftRoom = x + BUTTON - EDGE;
        const side = dragging?.expanded || rightRoom >= 320 || rightRoom >= leftRoom ? "left" : "right";
        const below = area.bottom - y, above = y + BUTTON - area.top;
        const row = dragging?.expanded || below >= panel.offsetHeight || below >= above ? "top" : "bottom";
        panel.dataset.toggleSide = side;
        panel.dataset.toggleRow = row;
        panel.style.width = `${snap(Math.min(320, side === "left" ? rightRoom : leftRoom))}px`;
        let height = row === "top" ? below : above;
        const left = side === "left" ? x : x + BUTTON - panel.offsetWidth;
        if (!favorites.hidden && left < EDGE + favorites.offsetWidth) {
            const short = area.bottom - area.top < 400;
            const reserve = short ? 96 : 128;
            const legendReserve = legend.hidden ? 0 : short ? 48 : Math.min(legend.scrollHeight, Math.max(48, (area.bottom - area.top) * .2));
            height = Math.max(120, height - reserve - legendReserve - EDGE * 2);
        }
        panel.classList.toggle("is-compact", height < 240);
        panel.style.maxHeight = `${Math.max(BUTTON, height)}px`;
        panel.style.left = `${snap(side === "left" ? 0 : BUTTON - panel.offsetWidth)}px`;
        panel.style.top = `${snap(row === "top" ? 0 : BUTTON - panel.offsetHeight)}px`;
    }

    function layout() {
        if (controller.suspended || !page.isConnected) return;
        const area = bounds();
        if (!dragging) {
            const position = controller.preferences.mapMenuPosition || {x: 0, y: 0};
            toolbar.style.left = `${snap(EDGE + position.x * Math.max(0, area.right - EDGE - BUTTON))}px`;
            toolbar.style.top = `${snap(area.top + position.y * Math.max(0, area.bottom - area.top - BUTTON))}px`;
        }
        layoutPanel(area);
        const obstacles = [relativeRect(panel.hidden ? toggle : panel, area)];
        const player = document.querySelector('#persistent-player[data-player-state="playing"]');
        if (player?.getBoundingClientRect().width) obstacles.push(relativeRect(player, area));
        const zoomRect = place(zoom, {left: area.right - zoom.offsetWidth, width: zoom.offsetWidth,
            height: zoom.scrollHeight, minimum: zoom.scrollHeight, bottom: true}, obstacles, area);
        if (zoomRect) obstacles.push(zoomRect);
        if (!legend.hidden) {
            legend.classList.remove("is-obscured");
            const compact = !panel.hidden && area.bottom - area.top < 400;
            const height = Math.min(legend.scrollHeight, compact ? 48 : Math.max(48, (area.bottom - area.top) * .2), 240);
            const rect = place(legend, {left: EDGE, width: legend.offsetWidth, height, minimum: 48, bottom: true}, obstacles, area);
            if (rect) obstacles.push(rect);
        }
        if (!favorites.hidden) {
            const rows = list.querySelectorAll("button:not([hidden])").length;
            const header = favorites.querySelector("header").offsetHeight;
            const height = header + Math.min(FAVORITE_ROWS, Math.max(rows, 1)) * FAVORITE_ROW + 8;
            place(favorites, {left: EDGE, width: favorites.offsetWidth, height, minimum: header + FAVORITE_ROW + 8}, obstacles, area);
        }
    }

    function renderMenu(expanded) {
        const newlyOpened = expanded && panel.hidden;
        panel.hidden = !expanded;
        toggle.hidden = expanded;
        toggle.setAttribute("aria-expanded", String(expanded));
        toolbar.classList.toggle("is-open", expanded);
        if (newlyOpened) {
            panel.style.removeProperty("max-height");
            panel.classList.remove("is-compact");
        }
    }

    function close({restoreFocus = false} = {}) {
        writeMapPreferences({...readMapPreferences(controller.countryCodes), mapMenuOpen: false}, controller.countryCodes);
        if (restoreFocus) toggle.focus({preventScroll: true});
    }

    function open() {
        if (controller.suspended || dragging) return;
        writeMapPreferences({...readMapPreferences(controller.countryCodes), mapMenuOpen: true}, controller.countryCodes);
        closeButton.focus({preventScroll: true});
    }

    function setDisplay(value) {
        writeMapPreferences({...readMapPreferences(controller.countryCodes), favoritesDisplay: value}, controller.countryCodes);
    }

    function refresh() {
        renderMenu(controller.preferences.mapMenuOpen);
        const mode = controller.preferences.favoritesDisplay;
        favorites.hidden = mode !== "list" || Boolean(controller.presetEditor?.active);
        favoritesToggle.setAttribute("aria-label", {hearts: "Show favorites as a list", list: "Hide favorites", none: "Show favorites as map hearts"}[mode]);
        favoritesToggle.setAttribute("aria-expanded", String(mode === "list"));
        for (const icon of favoritesToggle.querySelectorAll("[data-favorites-icon]")) icon.hidden = icon.dataset.favoritesIcon !== mode;
        const countries = [...controller.countriesByCode.values()].filter(country => controller.personal?.favorites.has(country.iso_a2))
            .sort((a, b) => a.name.localeCompare(b.name));
        const next = JSON.stringify([countries.map(country => [country.iso_a2, country.name, country.flag_url]), controller.personal?.ready]);
        if (next !== signature) {
            signature = next;
            list.replaceChildren();
            for (const country of countries) {
                const button = document.createElement("button");
                button.type = "button";
                button.dataset.mapFavoriteCountry = country.iso_a2;
                button.dataset.search = normalize(`${country.name} ${country.iso_a2}`);
                if (country.iso_a2 === controller.selectedCode) button.setAttribute("aria-current", "true");
                const flag = document.createElement("span");
                flag.className = "map-favorite-flag";
                flag.textContent = country.flag || country.iso_a2;
                if (country.flag_url) {
                    const image = new Image();
                    image.alt = ""; image.loading = "lazy"; image.referrerPolicy = "no-referrer";
                    image.addEventListener("error", () => { flag.textContent = country.flag || country.iso_a2; }, {once: true});
                    image.src = country.flag_url;
                    flag.replaceChildren(image);
                }
                const name = document.createElement("span");
                name.textContent = country.name;
                button.append(flag, name);
                list.append(button);
            }
            list.append(empty);
            search.hidden = countries.length <= FAVORITE_ROWS;
            if (search.hidden) setSearch(false);
            filterFavorites();
        }
        for (const button of list.querySelectorAll("button")) {
            if (button.dataset.mapFavoriteCountry === controller.selectedCode) button.setAttribute("aria-current", "true");
            else button.removeAttribute("aria-current");
        }
        layout();
    }

    toggle.addEventListener("click", event => {
        if (suppressClick) { suppressClick = false; event.preventDefault(); return; }
        open();
    }, {signal});
    toggle.addEventListener("keydown", event => {
        if (event.key !== "ArrowDown") return;
        event.preventDefault(); open();
    }, {signal});
    closeButton.addEventListener("click", () => close({restoreFocus: true}), {signal});
    panel.addEventListener("click", event => {
        if (event.target.closest("[data-map-favorites-toggle]")) {
            const next = (FAVORITES_DISPLAY_MODES.indexOf(controller.preferences.favoritesDisplay) + 1) % FAVORITES_DISPLAY_MODES.length;
            setDisplay(FAVORITES_DISPLAY_MODES[next]);
        }
    }, {signal});
    function filterFavorites() {
        const tokens = normalize(query.value.trim()).split(/\s+/).filter(Boolean);
        let visible = 0;
        for (const button of list.querySelectorAll("button")) {
            button.hidden = !tokens.every(token => button.dataset.search.includes(token));
            if (!button.hidden) visible++;
        }
        empty.hidden = visible > 0 || !controller.personal?.ready;
        empty.textContent = query.value.trim() ? "No matching favorites" : "No favorites yet";
        list.scrollTop = 0;
        scheduleLayout();
    }
    function setSearch(open) {
        favorites.classList.toggle("is-searching", open);
        searchToggle.setAttribute("aria-expanded", String(open));
        searchToggle.setAttribute("aria-label", open ? "Close favorites search" : "Search favorite countries");
        query.disabled = !open;
        query.setAttribute("aria-hidden", String(!open));
        query.tabIndex = open ? 0 : -1;
        if (open) query.focus({preventScroll: true});
        else { query.value = ""; filterFavorites(); }
    }
    searchToggle.addEventListener("click", () => setSearch(query.disabled), {signal});
    query.addEventListener("input", filterFavorites, {signal});
    query.addEventListener("keydown", event => {
        if (event.key !== "Escape") return;
        event.preventDefault(); event.stopPropagation(); setSearch(false); searchToggle.focus({preventScroll: true});
    }, {signal});
    list.addEventListener("click", event => {
        const button = event.target.closest("[data-map-favorite-country]");
        if (button) selectCountry(controller, button.dataset.mapFavoriteCountry, {fit: true, focusDrawer: true});
    }, {signal});
    function startDrag(event) {
        if (event.button !== 0) return;
        const expanded = event.currentTarget === menuBar;
        if (expanded && event.target.closest("button, a, input, select")) return;
        const rect = (expanded ? panel : toggle).getBoundingClientRect(), area = bounds();
        dragging = {id: event.pointerId, x: event.clientX, y: event.clientY,
            left: rect.left - area.rect.left, top: rect.top - area.rect.top, moved: false, expanded};
        event.currentTarget.setPointerCapture(event.pointerId);
    }
    function moveDrag(event) {
        if (!dragging || dragging.id !== event.pointerId) return;
        const dx = event.clientX - dragging.x, dy = event.clientY - dragging.y;
        if (!dragging.moved && Math.hypot(dx, dy) < 6) return;
        if (!dragging.moved) { dragging.moved = true; toolbar.classList.add("is-dragging"); }
        const area = bounds();
        const width = dragging.expanded ? panel.offsetWidth : BUTTON;
        const height = dragging.expanded ? panel.offsetHeight : BUTTON;
        toolbar.style.left = `${snap(clamp(dragging.left + dx, EDGE, Math.max(EDGE, area.right - width)))}px`;
        toolbar.style.top = `${snap(clamp(dragging.top + dy, area.top, Math.max(area.top, area.bottom - height)))}px`;
        scheduleLayout();
    }
    function endDrag(event, save = true) {
        if (!dragging || dragging.id !== event.pointerId) return;
        const moved = dragging.moved;
        dragging = null;
        toolbar.classList.remove("is-dragging");
        if (!moved) return;
        suppressClick = true;
        setTimeout(() => { suppressClick = false; }, 0);
        if (save) {
            const area = bounds();
            const x = clamp((parseFloat(toolbar.style.left) - EDGE) / Math.max(1, area.right - EDGE - BUTTON), 0, 1);
            const y = clamp((parseFloat(toolbar.style.top) - area.top) / Math.max(1, area.bottom - area.top - BUTTON), 0, 1);
            writeMapPreferences({...readMapPreferences(controller.countryCodes), mapMenuPosition: {x, y}}, controller.countryCodes);
        } else layout();
    }
    for (const handle of [toggle, menuBar]) {
        handle.addEventListener("pointerdown", startDrag, {signal});
        handle.addEventListener("pointermove", moveDrag, {signal});
        handle.addEventListener("pointerup", event => endDrag(event), {signal});
        handle.addEventListener("pointercancel", event => endDrag(event, false), {signal});
        handle.addEventListener("lostpointercapture", event => endDrag(event, false), {signal});
    }

    function updateZoom() {
        if (!controller.map) return;
        page.querySelector('[data-map-zoom="in"]').disabled = controller.map.getZoom() >= controller.map.getMaxZoom();
        page.querySelector('[data-map-zoom="out"]').disabled = controller.map.getZoom() <= controller.map.getMinZoom();
    }
    zoom.addEventListener("click", event => {
        const button = event.target.closest("[data-map-zoom]");
        if (!button || !controller.map) return;
        const options = {duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 200};
        if (button.dataset.mapZoom === "in") controller.map.zoomIn(options);
        else controller.map.zoomOut(options);
    }, {signal});
    const observer = new ResizeObserver(scheduleLayout);
    observer.observe(workspace);
    const header = document.querySelector(".app-header");
    if (header) observer.observe(header);
    if (legend) observer.observe(legend);
    const player = document.querySelector("#persistent-player");
    if (player) observer.observe(player);
    const visibility = new MutationObserver(scheduleLayout);
    for (const drawer of page.querySelectorAll(".country-drawer")) {
        observer.observe(drawer);
        visibility.observe(drawer, {attributes: true, attributeFilter: ["hidden"]});
    }
    if (player) visibility.observe(player, {attributes: true, attributeFilter: ["data-player-state", "class"]});
    window.addEventListener("resize", scheduleLayout, {signal});
    window.addEventListener("scroll", scheduleLayout, {signal, passive: true});
    document.addEventListener("world-journal:player-moved", scheduleLayout, {signal});
    signal.addEventListener("abort", () => { cancelAnimationFrame(frame); observer.disconnect(); visibility.disconnect(); }, {once: true});
    refresh();
    return {close, refresh, layout, attachMap(map) { map.on("zoom", updateZoom); updateZoom(); }};
}
