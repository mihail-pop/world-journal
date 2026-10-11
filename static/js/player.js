const POSITION_KEY = "world-journal:player-position";
const VIDEO_ID_PATTERN = /^[A-Za-z0-9_-]{11}$/;
let initialized = false;
let apiPromise;

// Load YouTube's supported control API only after the user starts a video.
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
    if (initialized) return;
    const player = document.querySelector("#persistent-player");
    if (!player) return;
    initialized = true;
    const stage = player.querySelector("[data-player-stage]");
    const playback = player.querySelector("[data-player-play-pause]");
    const expand = player.querySelector("[data-player-expand]");
    const drag = player.querySelector("[data-player-drag]");
    const toggle = document.querySelector("[data-player-toggle]");
    const bookmark = player.querySelector("[data-player-bookmark]");
    const notice = player.querySelector("[data-player-notice]");
    let api = null;
    let position = null;
    let dragging = null;
    let layoutFrame = null;
    try {
        const stored = JSON.parse(localStorage.getItem(POSITION_KEY));
        if (stored && [stored.x, stored.y].every(value => Number.isFinite(value) && value >= 0 && value <= 1)) position = stored;
    } catch { /* The default dock works without local storage. */ }

    function bounds() {
        const headerBottom = document.querySelector(".app-header").getBoundingClientRect().bottom;
        const rect = player.getBoundingClientRect();
        const top = Math.max(8, headerBottom + 8);
        return {left: 8, top, width: Math.max(0, document.documentElement.clientWidth - rect.width - 16),
            height: Math.max(0, window.innerHeight - rect.height - top - 8)};
    }

    function syncLayout() {
        layoutFrame = null;
        const active = player.dataset.playerState !== "empty";
        const expanded = player.classList.contains("is-expanded");
        if (active && !expanded && position) {
            const limit = bounds();
            player.style.left = `${limit.left + position.x * limit.width}px`;
            player.style.top = `${limit.top + position.y * limit.height}px`;
            player.style.right = "auto";
            player.style.bottom = "auto";
        }
        const rect = player.getBoundingClientRect();
        const workspace = document.querySelector(".map-workspace")?.getBoundingClientRect();
        const drawer = document.querySelector("[data-country-drawer]")?.getBoundingClientRect();
        const overlapsDrawer = drawer && rect.left < drawer.right && rect.right > drawer.left;
        const mapOffset = active && !expanded && workspace && overlapsDrawer
            ? Math.max(12, workspace.bottom - rect.top + 16) : 12;
        document.documentElement.style.setProperty("--persistent-player-height", `${active && !expanded ? rect.height : 0}px`);
        document.documentElement.style.setProperty("--persistent-player-map-offset", `${mapOffset}px`);
        document.dispatchEvent(new CustomEvent("world-journal:player-moved"));
    }
    function scheduleLayout() {
        if (layoutFrame === null) layoutFrame = requestAnimationFrame(syncLayout);
    }
    function resetPositionStyles() {
        for (const property of ["top", "left", "right", "bottom"]) player.style.removeProperty(property);
    }
    function setExpanded(value) {
        if (value && player.classList.contains("is-minimized")) setMinimized(false);
        player.classList.toggle("is-expanded", value);
        expand.setAttribute("aria-pressed", String(value));
        expand.title = value ? "Return to small player" : "Expand to app view";
        expand.setAttribute("aria-label", expand.title);
        expand.querySelector("[data-player-expand-icon]").hidden = value;
        expand.querySelector("[data-player-contract-icon]").hidden = !value;
        drag.disabled = value;
        resetPositionStyles();
        syncLayout();
    }
    function setMinimized(value) {
        if (value) setExpanded(false);
        player.classList.toggle("is-minimized", value);
        const minimize = player.querySelector("[data-player-minimize]");
        minimize.title = value ? "Restore video player" : "Minimize video player";
        minimize.setAttribute("aria-label", minimize.title);
        minimize.querySelector("[data-player-minimize-icon]").hidden = value;
        minimize.querySelector("[data-player-restore-icon]").hidden = !value;
        toggle.hidden = !value;
        toggle.setAttribute("aria-expanded", String(!value));
        syncLayout();
    }
    function setPlayback(playing) {
        playback.dataset.playing = String(playing);
        playback.title = playing ? "Pause" : "Play";
        playback.setAttribute("aria-label", playing ? "Pause video" : "Play video");
        playback.querySelector("[data-player-play-icon]").hidden = playing;
        playback.querySelector("[data-player-pause-icon]").hidden = !playing;
    }
    function showNotice(message) {
        notice.querySelector("[data-player-notice-text]").textContent = message;
        notice.hidden = false;
    }
    function stop() {
        api?.destroy();
        api = null;
        stage.replaceChildren();
        player.dataset.playerState = "empty";
        setMinimized(false);
        setExpanded(false);
        playback.disabled = true;
        notice.hidden = true;
    }
    async function play(detail) {
        const videoId = detail?.videoId;
        const start = detail?.startSeconds ?? 0;
        if (!VIDEO_ID_PATTERN.test(videoId ?? "") || !Number.isSafeInteger(start) || start < 0 || start > 2147483647) return;
        const title = typeof detail.title === "string" && detail.title.trim() ? detail.title.trim() : "YouTube video";
        api?.destroy();
        api = null;
        const iframe = document.createElement("iframe");
        const params = new URLSearchParams({autoplay: "1", enablejsapi: "1", origin: location.origin, playsinline: "1"});
        if (start) params.set("start", start);
        iframe.id = "shell-video-iframe";
        iframe.src = `https://www.youtube-nocookie.com/embed/${videoId}?${params}`;
        iframe.title = `${title} on YouTube`;
        iframe.allow = "autoplay; encrypted-media; picture-in-picture";
        iframe.referrerPolicy = "strict-origin-when-cross-origin";
        iframe.allowFullscreen = true;
        stage.replaceChildren(iframe);
        player.dataset.playerState = "playing";
        player.setAttribute("aria-label", `${title} · video player`);
        setMinimized(false);
        setPlayback(false);
        playback.disabled = true;
        notice.hidden = true;
        notice.querySelector("[data-player-external]").href = `https://www.youtube.com/watch?v=${videoId}`;
        const saveUrl = new URL(document.body.dataset.journalNewUrl, location.origin);
        saveUrl.search = new URLSearchParams({type: "youtube", video: videoId, title, source: detail.channel || "YouTube"});
        // Only the app's Journal links may become the player's bookmark target.
        let supplied;
        try { supplied = new URL(detail.saveUrl, location.origin); } catch { /* Use the validated video's default link. */ }
        const validSupplied = supplied?.origin === location.origin && (supplied.pathname === saveUrl.pathname || /^\/journal\/[a-f0-9-]{36}\/edit\/$/.test(supplied.pathname));
        bookmark.removeAttribute("data-bookmark-url");
        bookmark.removeAttribute("hx-get");
        bookmark.href = validSupplied ? supplied.href : saveUrl.href;
        window.htmx.process(bookmark);
        document.dispatchEvent(new CustomEvent("world-journal:player-bookmark-changed"));
        scheduleLayout();
        try {
            const YT = await loadPlayerApi();
            if (stage.querySelector("iframe") !== iframe) return;
            api = new YT.Player(iframe, {host: "https://www.youtube-nocookie.com", events: {
                onReady(event) {
                    if (stage.querySelector("iframe") !== iframe) return;
                    playback.disabled = false;
                    setPlayback(event.target.getPlayerState() === YT.PlayerState.PLAYING);
                },
                onStateChange(event) {
                    if (stage.querySelector("iframe") === iframe) setPlayback(event.data === YT.PlayerState.PLAYING || event.data === YT.PlayerState.BUFFERING);
                },
                onError() {
                    if (stage.querySelector("iframe") !== iframe) return;
                    playback.disabled = true;
                    showNotice("This video cannot be played here.");
                },
            }});
        } catch (error) {
            if (stage.querySelector("iframe") === iframe) showNotice(error.message);
        }
    }
    function rememberPosition(left, top) {
        const limit = bounds();
        position = {x: limit.width ? Math.max(0, Math.min(1, (left - limit.left) / limit.width)) : 0,
            y: limit.height ? Math.max(0, Math.min(1, (top - limit.top) / limit.height)) : 0};
        scheduleLayout();
    }
    function persistPosition() {
        try { localStorage.setItem(POSITION_KEY, JSON.stringify(position)); } catch { /* Movement still works. */ }
    }
    drag.addEventListener("pointerdown", event => {
        if (event.button !== 0 || drag.disabled) return;
        event.preventDefault();
        const rect = player.getBoundingClientRect();
        dragging = {id: event.pointerId, x: event.clientX - rect.left, y: event.clientY - rect.top};
        drag.setPointerCapture(event.pointerId);
        player.classList.add("is-dragging");
    });
    drag.addEventListener("pointermove", event => {
        if (!dragging || dragging.id !== event.pointerId) return;
        rememberPosition(event.clientX - dragging.x, event.clientY - dragging.y);
    });
    function finishDrag() {
        if (!dragging) return;
        dragging = null;
        player.classList.remove("is-dragging");
        persistPosition();
    }
    for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) drag.addEventListener(type, finishDrag);
    drag.addEventListener("keydown", event => {
        const offsets = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]};
        if (!offsets[event.key]) return;
        event.preventDefault();
        const rect = player.getBoundingClientRect();
        const step = event.shiftKey ? 40 : 10;
        rememberPosition(rect.left + offsets[event.key][0] * step, rect.top + offsets[event.key][1] * step);
        persistPosition();
    });
    playback.addEventListener("click", () => {
        if (!api || playback.disabled) return;
        if (playback.dataset.playing === "true") api.pauseVideo();
        else api.playVideo();
    });
    expand.addEventListener("click", () => setExpanded(!player.classList.contains("is-expanded")));
    player.querySelector("[data-player-minimize]").addEventListener("click", () => setMinimized(!player.classList.contains("is-minimized")));
    toggle.addEventListener("click", () => setMinimized(false));
    player.querySelector("[data-player-close]").addEventListener("click", stop);
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && player.classList.contains("is-expanded")) {
            event.preventDefault();
            event.stopImmediatePropagation();
            setExpanded(false);
            expand.focus({preventScroll: true});
        }
    });
    document.addEventListener("world-journal:play-video", event => play(event.detail));
    document.addEventListener("world-journal:page-ready", scheduleLayout);
    window.addEventListener("resize", scheduleLayout);
    window.visualViewport?.addEventListener("resize", scheduleLayout);
    new ResizeObserver(scheduleLayout).observe(player);
}
