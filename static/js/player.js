import { iconPlay, iconPause, iconPrev, iconNext, iconInfo, iconTheater, iconSmall,
    iconFsEnter, iconFsExit, iconClose, iconHistory, iconHeart } from "./player_icons.js";

const PREFIX = "world-journal:player:";
const STATE = `${PREFIX}state`, LEASE = `${PREFIX}owner`, COMMAND = `${PREFIX}command`, LAYOUT = `${PREFIX}layout`;
const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/;
let initialized = false;
let apiPromise;

function read(key, fallback = null, storage = localStorage) {
    try { return JSON.parse(storage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function write(key, value, storage = localStorage) {
    try {
        if (value === null) storage.removeItem(key);
        else storage.setItem(key, JSON.stringify(value));
    } catch { /* Playback also works when browser storage is unavailable. */ }
}
function video(detail) {
    if (!detail || !VIDEO_ID.test(detail.videoId)) return null;
    const start = Number(detail.startSeconds ?? 0);
    let saveUrl;
    try {
        const url = new URL(detail.saveUrl, location.origin);
        if (url.origin === location.origin && (/^\/journal\/[a-f0-9-]{36}\/edit\/$/.test(url.pathname) || url.pathname === "/journal/new/")) saveUrl = url.href;
    } catch { /* Build a Journal link from the validated video below. */ }
    return {videoId: detail.videoId, title: String(detail.title || "YouTube video").slice(0, 300), saveUrl,
        channel: String(detail.channel || "YouTube").slice(0, 200),
        startSeconds: Number.isFinite(start) ? Math.max(0, Math.min(2147483647, Math.floor(start))) : 0};
}
function loadPlayerApi() {
    if (window.YT?.Player) return Promise.resolve(window.YT);
    if (apiPromise) return apiPromise;
    apiPromise = new Promise((resolve, reject) => {
        const previous = window.onYouTubeIframeAPIReady;
        const script = document.createElement("script");
        const timeout = setTimeout(fail, 15000);
        function fail() {
            clearTimeout(timeout);
            script.remove();
            window.onYouTubeIframeAPIReady = previous;
            apiPromise = null;
            reject(new Error("Extra playback controls are unavailable. Use the video controls."));
        }
        window.onYouTubeIframeAPIReady = () => {
            clearTimeout(timeout);
            window.onYouTubeIframeAPIReady = previous;
            previous?.();
            resolve(window.YT);
        };
        script.src = "https://www.youtube.com/iframe_api";
        script.async = true;
        script.onerror = fail;
        document.head.append(script);
    });
    return apiPromise;
}

export function initializePlayer() {
    const root = document.querySelector("#persistent-player");
    if (initialized || !root) return;
    initialized = true;
    const popout = document.body.dataset.playerPopout === "true";
    const tabKey = `${PREFIX}${popout ? "popup-tab" : "tab"}`;
    const tab = read(tabKey, null, sessionStorage) || crypto.randomUUID();
    write(tabKey, tab, sessionStorage);
    const byId = id => root.querySelector(`#mp-${id}`);
    const wrapper = byId("wrapper"), controls = byId("controls"), history = byId("history");
    const mount = root.querySelector("#music-player"), notice = byId("notice");
    const playback = byId("playpause"), heart = byId("heart"), info = byId("info");
    let layout = read(LAYOUT, {}), session = null, api = null, generation = 0, ready = false;
    let favorite = false, popupWindow = null, layoutFrame = null, drag = null, leaving = false;
    let returning = false, lockedScroll = null, favoriteRequest = null, popupFallback = null, releasedAt = 0;
    let heartbeat = null, waitingForPopup = false;

    for (const [id, svg] of Object.entries({prev: iconPrev, next: iconNext, info: iconInfo,
        "toggle-hist": iconHistory, dock: iconTheater, close: iconClose, playpause: iconPlay})) byId(id).innerHTML = svg;
    heart.innerHTML = iconHeart(false);
    byId("popout").insertAdjacentHTML("afterbegin", iconInfo);
    if (popout) { info.target = "world-journal-main"; info.removeAttribute("hx-boost"); }

    function lease() { return read(LEASE); }
    function alive(owner = lease()) { return owner && Date.now() - owner.at < 120000; }
    function ownsPlayer() { return lease()?.tab === tab; }
    function claim() { write(LEASE, {tab, popup: popout, at: Date.now()}); }
    function release() { if (ownsPlayer()) write(LEASE, null); }
    function syncHeartbeat() {
        if ((session || waitingForPopup) && heartbeat === null) heartbeat = setInterval(tick, 2000);
        else if (!session && !waitingForPopup && heartbeat !== null) { clearInterval(heartbeat); heartbeat = null; }
    }
    function current() { return session?.history[session.index]; }
    function snapshot() {
        if (!session) return null;
        try {
            if (ready) {
                session.time = Math.max(0, api.getCurrentTime() || 0);
                const state = api.getPlayerState();
                if (state === 1 || state === 3) session.paused = false;
                else if (state === 2 || state === 0) session.paused = true;
            }
        } catch { /* Keep the last known position while YouTube is loading. */ }
        return session;
    }
    function persist() { if (session && ownsPlayer()) write(STATE, snapshot()); }
    function lockScroll(lock) {
        if (lock && lockedScroll === null) lockedScroll = {x: scrollX, y: scrollY};
        document.documentElement.classList.toggle("wj-player-scroll-locked", lock);
        document.body.classList.toggle("wj-player-scroll-locked", lock);
        if (!lock && lockedScroll) {
            const position = lockedScroll;
            lockedScroll = null;
            window.scrollTo(position.x, position.y);
        }
    }
    function updateOffsets() {
        const active = Boolean(session), fullscreen = !popout && active && layout.fullscreen;
        const rect = root.getBoundingClientRect();
        const workspace = document.querySelector(".map-workspace")?.getBoundingClientRect();
        const drawer = document.querySelector("[data-country-drawer]")?.getBoundingClientRect();
        const overlaps = drawer && rect.left < drawer.right && rect.right > drawer.left;
        const offset = active && !fullscreen && workspace && overlaps ? Math.max(12, workspace.bottom - rect.top + 16) : 12;
        document.documentElement.style.setProperty("--persistent-player-height", `${active && !fullscreen ? rect.height : 0}px`);
        document.documentElement.style.setProperty("--persistent-player-map-offset", `${offset}px`);
        document.dispatchEvent(new CustomEvent("world-journal:player-moved"));
    }
    function position(x, y) {
        const rect = root.getBoundingClientRect();
        const left = Math.max(0, Math.min(x, innerWidth - rect.width));
        const top = Math.max(0, Math.min(y, innerHeight - rect.height));
        Object.assign(root.style, {left: `${left}px`, top: `${top}px`, right: "auto", bottom: "auto"});
        return {x: left, y: top};
    }
    function size() {
        layoutFrame = null;
        const fullscreen = !popout && Boolean(session) && Boolean(layout.fullscreen);
        const portrait = matchMedia("(orientation: portrait)").matches || innerHeight > innerWidth;
        root.classList.toggle("mp-fullscreen", fullscreen);
        wrapper.classList.toggle("mp-fullscreen", fullscreen);
        wrapper.classList.toggle("mp-portrait", portrait);
        wrapper.classList.toggle("mp-popout", popout);
        lockScroll(fullscreen);
        history.style.display = layout.history ? "flex" : "none";
        controls.style.height = "";
        history.style.width = "";
        if (popout || fullscreen) {
            Object.assign(root.style, {top: "0", left: "0", right: "0", bottom: "0", width: "100%", height: "100%", borderRadius: "0", zIndex: fullscreen ? "99999" : "9999"});
            if (popout) controls.style.height = "40px";
        } else {
            const scale = portrait ? 1.5 : 1;
            let width = (layout.medium ? 480 : 384) * scale;
            if (portrait) {
                const css = getComputedStyle(controls);
                width = Math.min(Math.max(width, parseFloat(css.minWidth) || 0), Math.max(1, innerWidth - 2 * (parseFloat(css.paddingLeft) || 0)));
            }
            const controlsHeight = portrait ? Math.ceil(controls.getBoundingClientRect().height) : 40 * scale;
            const historyWidth = layout.history && !portrait ? 200 * scale : 0;
            Object.assign(root.style, {width: `${width + historyWidth}px`, height: `${width * 9 / 16 + controlsHeight}px`, borderRadius: "8px", zIndex: "9999", left: portrait ? "auto" : "20px", top: portrait ? "0" : "auto", right: portrait ? "0" : "auto", bottom: portrait ? "auto" : "20px"});
            controls.style.height = `${controlsHeight}px`;
            if (!portrait) history.style.width = `${historyWidth}px`;
            if (Number.isFinite(layout.position?.x) && Number.isFinite(layout.position?.y)) position(layout.position.x, layout.position.y);
        }
        wrapper.style.setProperty("--mp-controls-height", `${Math.ceil(controls.getBoundingClientRect().height)}px`);
        byId("expand").innerHTML = layout.medium ? iconTheater : iconSmall;
        byId("expand").title = layout.medium ? "Small Mode" : "Medium Mode";
        byId("expand").setAttribute("aria-label", byId("expand").title);
        byId("fullscreen").innerHTML = fullscreen ? iconFsExit : iconFsEnter;
        byId("fullscreen").title = fullscreen ? "Exit Fullscreen" : "Fullscreen";
        byId("fullscreen").setAttribute("aria-label", byId("fullscreen").title);
        byId("toggle-hist").setAttribute("aria-pressed", String(Boolean(layout.history)));
        updateOffsets();
    }
    function scheduleSize() { if (layoutFrame === null) layoutFrame = requestAnimationFrame(size); }
    function saveLayout() { write(LAYOUT, layout); size(); }
    function setPlaying(playing) {
        playback.innerHTML = playing ? iconPause : iconPlay;
        playback.title = playing ? "Pause" : "Play";
        playback.setAttribute("aria-label", playback.title);
    }
    function showNotice(message) { notice.querySelector("span").textContent = message; notice.hidden = false; }
    function destroy() {
        generation++;
        ready = false;
        api?.destroy();
        api = null;
        mount.replaceChildren();
        playback.disabled = true;
        favoriteRequest?.abort();
    }
    function hide() { destroy(); session = null; root.dataset.playerState = "empty"; size(); syncHeartbeat(); }
    function journalUrl(item) {
        if (item.saveUrl) return item.saveUrl;
        const url = new URL(document.body.dataset.journalNewUrl, location.origin);
        url.search = new URLSearchParams({type: "youtube", video: item.videoId, title: item.title, source: item.channel});
        return url.href;
    }
    function updateFavorite(result) {
        favorite = Boolean(result.favorite);
        heart.innerHTML = iconHeart(favorite);
        heart.setAttribute("aria-pressed", String(favorite));
        heart.title = favorite ? "Remove from Journal favorites" : "Favorite in Journal";
        info.href = result.edit_url || journalUrl(current());
        window.htmx?.process(info);
    }
    async function favoriteStatus(item, desired) {
        favoriteRequest?.abort();
        const controller = new AbortController();
        favoriteRequest = controller;
        const changing = typeof desired === "boolean";
        const body = new URL(journalUrl(item)).searchParams;
        for (const [key, value] of Object.entries({favorite: String(desired), title: item.title, channel: item.channel})) body.set(key, value);
        heart.disabled = true;
        try {
            const response = await fetch(root.dataset.videoUrl.replace("VIDEOIDHERE", item.videoId), {
                method: changing ? "POST" : "GET", signal: controller.signal,
                headers: {"Accept": "application/json", "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content},
                ...(changing ? {body} : {}),
            });
            if (!response.ok) throw new Error("Could not update Journal favorites. Try again.");
            const result = await response.json();
            if (current()?.videoId !== item.videoId || favoriteRequest !== controller) return;
            updateFavorite(result);
            if (changing) document.dispatchEvent(new CustomEvent("world-journal:data-changed", {detail: {path: "/journal/"}}));
        } catch (error) { if (error.name !== "AbortError" && changing) showNotice(error.message); }
        finally { if (favoriteRequest === controller) heart.disabled = false; }
    }
    function queuedNext() {
        if (!session?.queue.length) return null;
        const index = session.queue.findIndex(item => item.videoId === current()?.videoId);
        return session.queue[(index + 1) % session.queue.length];
    }
    function renderHistory() {
        history.replaceChildren();
        if (!session) return;
        session.history.forEach((item, index) => {
            const row = document.createElement("div");
            row.className = `history-item${index === session.index ? " active" : ""}`;
            row.tabIndex = 0;
            row.setAttribute("role", "button");
            const title = document.createElement("div");
            title.className = "mp-history-title";
            title.textContent = item.title;
            title.title = item.title;
            row.append(title);
            const select = () => { session.index = index; session.time = item.startSeconds; session.paused = false; void renderVideo(); };
            row.addEventListener("click", select);
            row.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); } });
            history.append(row);
        });
        history.querySelector(".active")?.scrollIntoView({behavior: "smooth", block: "nearest"});
    }
    async function renderVideo() {
        destroy();
        const token = generation, item = current();
        if (!item) return;
        waitingForPopup = false;
        claim();
        syncHeartbeat();
        root.dataset.playerState = "playing";
        root.setAttribute("aria-label", `${item.title} · video player`);
        if (popout) document.title = `${item.title} - World Journal`;
        notice.hidden = true;
        notice.querySelector("a").href = `https://www.youtube.com/watch?v=${item.videoId}`;
        updateFavorite({favorite: false});
        void favoriteStatus(item);
        renderHistory();
        size();
        const iframe = document.createElement("iframe");
        const params = new URLSearchParams({autoplay: session.paused ? "0" : "1", enablejsapi: "1", origin: location.origin, playsinline: "1", start: String(Math.floor(session.time || 0))});
        iframe.src = `https://www.youtube-nocookie.com/embed/${item.videoId}?${params}`;
        iframe.title = `${item.title} on YouTube`;
        iframe.allow = "autoplay; encrypted-media; picture-in-picture";
        iframe.referrerPolicy = "strict-origin-when-cross-origin";
        iframe.allowFullscreen = true;
        mount.append(iframe);
        setPlaying(false);
        persist();
        try {
            const YT = await loadPlayerApi();
            if (token !== generation) return;
            api = new YT.Player(iframe, {host: "https://www.youtube-nocookie.com", events: {
                onReady(event) {
                    if (token !== generation) return;
                    ready = true;
                    playback.disabled = false;
                    if (session.paused) event.target.pauseVideo(); else event.target.playVideo();
                    setPlaying(event.target.getPlayerState() === 1);
                },
                onStateChange(event) {
                    if (token !== generation) return;
                    setPlaying(event.data === 1 || event.data === 3);
                    if (event.data === 0) next(true); else persist();
                },
                onError() { if (token === generation) showNotice("This video cannot be played here."); },
            }});
        } catch (error) { if (token === generation) showNotice(error.message); }
    }
    function visibleQueue() {
        const unique = new Map();
        for (const button of document.querySelectorAll("[data-video-id][data-video-title]")) {
            const item = video({videoId: button.dataset.videoId, title: button.dataset.videoTitle, channel: button.dataset.videoChannel, startSeconds: button.dataset.videoStart});
            if (item) unique.set(item.videoId, item);
        }
        return [...unique.values()].slice(0, 200);
    }
    function start(detail, queue = visibleQueue()) {
        const item = video(detail);
        if (!item) return;
        const owner = lease();
        if (!popout && alive(owner) && owner.popup) {
            write(COMMAND, {id: crypto.randomUUID(), type: "play", detail: item, queue});
            popupWindow?.focus();
            return;
        }
        if (!session) session = {history: [], index: -1, queue: [], owner: tab, returnTo: tab, time: 0, paused: false};
        session.history = session.history.slice(0, session.index + 1);
        session.history.push(item);
        if (session.history.length > 200) session.history.shift();
        session.index = session.history.length - 1;
        session.queue = queue.map(video).filter(Boolean).slice(0, 200);
        session.time = item.startSeconds;
        session.paused = false;
        session.owner = popout ? "popup" : tab;
        void renderVideo();
    }
    function next(ended = false) {
        if (!session) return;
        if (session.index < session.history.length - 1) {
            session.index++;
            session.time = current().startSeconds;
            session.paused = false;
            void renderVideo();
        } else {
            const item = queuedNext();
            if (item) start(item, session.queue);
            else if (ended) { session.paused = true; persist(); }
        }
    }
    function restore(saved) {
        if (!saved || !Array.isArray(saved.history)) return;
        const items = saved.history.map(video);
        if (!items.length || items.some(item => !item) || items.length > 200 || !Number.isInteger(saved.index) || !items[saved.index]) return;
        session = {...saved, history: items, queue: (Array.isArray(saved.queue) ? saved.queue : []).map(video).filter(Boolean).slice(0, 200)};
        session.time = Number.isFinite(saved.time) ? Math.max(0, Math.min(saved.time, 2147483647)) : current().startSeconds;
        session.owner = popout ? "popup" : tab;
        session.returnTo = popout ? saved.returnTo : tab;
        void renderVideo();
    }
    function close() {
        waitingForPopup = false;
        write(STATE, null);
        release();
        hide();
        if (popout) { returning = true; window.close(); }
    }
    function popOut() {
        if (!session || popout) return;
        const popup = layout.popup || {};
        const width = Math.max(320, popup.width || 640), height = Math.max(240, popup.height || 400);
        popupWindow = window.open(root.dataset.popoutUrl, "world-journal-video-player", `popup,width=${width},height=${height},left=${popup.x ?? 20},top=${popup.y ?? Math.max(0, screen.availHeight - height - 20)},resizable=yes,scrollbars=no`);
        if (!popupWindow) { showNotice("Allow pop-up windows to open the separate player."); return; }
        const saved = {...snapshot(), owner: "popup", returnTo: tab};
        waitingForPopup = true;
        release();
        write(STATE, saved);
        hide();
        popupWindow.focus();
    }
    function dock() {
        if (!popout || !session) return;
        const saved = {...snapshot(), owner: session.returnTo};
        returning = true;
        release();
        hide();
        write(STATE, saved);
        if (window.opener && !window.opener.closed) {
            window.opener.postMessage({type: "world-journal:player-dock"}, location.origin);
            window.opener.focus();
        } else window.open("/", "world-journal-main");
        window.close();
    }
    function recoverPopup() {
        if (popout || session || leaving || Date.now() - releasedAt < 1700) return;
        const saved = read(STATE);
        if (saved?.owner === "popup" && saved.returnTo === tab && !alive()) restore(saved);
    }
    playback.addEventListener("click", () => {
        if (!ready) return;
        if (api.getPlayerState() === 1 || api.getPlayerState() === 3) { session.paused = true; api.pauseVideo(); }
        else { session.paused = false; api.playVideo(); }
        persist();
    });
    heart.addEventListener("click", () => { if (current()) void favoriteStatus(current(), !favorite); });
    byId("prev").addEventListener("click", () => {
        if (!session || session.index <= 0) return;
        session.index--;
        session.time = current().startSeconds;
        session.paused = false;
        void renderVideo();
    });
    byId("next").addEventListener("click", () => next());
    byId("expand").addEventListener("click", () => { layout.medium = !layout.medium; layout.fullscreen = false; saveLayout(); });
    byId("fullscreen").addEventListener("click", () => { layout.fullscreen = !layout.fullscreen; saveLayout(); });
    byId("toggle-hist").addEventListener("click", () => { layout.history = !layout.history; saveLayout(); if (layout.history) renderHistory(); });
    byId("popout").addEventListener("click", popOut);
    byId("dock").addEventListener("click", dock);
    byId("close").addEventListener("click", close);
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && layout.fullscreen && session) { layout.fullscreen = false; saveLayout(); }
    });
    for (const zone of root.querySelectorAll(".mp-drag-zone")) {
        zone.addEventListener("pointerdown", event => {
            if (event.button !== 0 || popout || layout.fullscreen) return;
            event.preventDefault();
            const rect = root.getBoundingClientRect();
            drag = {id: event.pointerId, x: event.clientX, y: event.clientY, left: rect.left, top: rect.top, moving: false};
            zone.setPointerCapture(event.pointerId);
        });
        zone.addEventListener("pointermove", event => {
            if (!drag || event.pointerId !== drag.id) return;
            const x = event.clientX - drag.x, y = event.clientY - drag.y;
            if (!drag.moving && Math.hypot(x, y) < 3) return;
            drag.moving = true;
            zone.classList.add("is-dragging"); root.classList.add("mp-dragging");
            layout.position = position(drag.left + x, drag.top + y);
            updateOffsets();
        });
        const finish = () => {
            if (!drag) return;
            if (drag.moving) write(LAYOUT, layout);
            drag = null;
            zone.classList.remove("is-dragging"); root.classList.remove("mp-dragging");
        };
        for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) zone.addEventListener(type, finish);
    }
    document.addEventListener("world-journal:play-video", event => start(event.detail));
    document.addEventListener("world-journal:page-ready", scheduleSize);
    window.addEventListener("resize", scheduleSize);
    window.visualViewport?.addEventListener("resize", scheduleSize);
    window.addEventListener("storage", event => {
        if (event.key === LEASE) {
            const owner = lease();
            if (session && owner && owner.tab !== tab) hide();
            if (!owner) {
                releasedAt = Date.now();
                clearTimeout(popupFallback);
                popupFallback = setTimeout(recoverPopup, 1750);
            }
        } else if (event.key === STATE) {
            const saved = read(STATE);
            if (!saved) { waitingForPopup = false; hide(); release(); }
            else if (!popout && !session && saved.owner === tab) restore(saved);
        } else if (event.key === COMMAND && popout && session) {
            const command = read(COMMAND);
            if (command?.type === "play") start(command.detail, command.queue);
        } else if (event.key === LAYOUT) { layout = read(LAYOUT, {}); size(); }
    });
    window.addEventListener("message", event => {
        if (event.origin !== location.origin || event.data?.type !== "world-journal:player-dock" || popout || session) return;
        const saved = read(STATE);
        if (saved?.owner === tab) restore(saved);
    });
    window.addEventListener("pagehide", () => {
        leaving = true;
        if (!returning) persist();
        release();
        lockScroll(false);
    });
    window.addEventListener("pageshow", event => {
        leaving = false;
        if (!event.persisted) return;
        const owner = lease();
        if (alive(owner) && owner.tab !== tab) hide();
        else if (session) { claim(); size(); }
        else recoverPopup();
    });
    // Browser-local playback snapshots; no database polling or background server writes.
    function tick() {
        if (leaving) return;
        if (session && ownsPlayer()) {
            claim(); persist();
            if (popout) {
                const popup = {x: screenX, y: screenY, width: outerWidth, height: outerHeight};
                if (JSON.stringify(layout.popup) !== JSON.stringify(popup)) { layout.popup = popup; write(LAYOUT, layout); }
            }
        } else recoverPopup();
    }
    const saved = read(STATE), owner = lease();
    waitingForPopup = !popout && saved?.owner === "popup" && saved.returnTo === tab;
    syncHeartbeat();
    if (saved && (!alive(owner) || owner.tab === tab) && (!popout || saved.owner === "popup")) restore(saved);
    else size();
}
