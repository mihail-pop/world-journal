const MINIMIZED_KEY = "world-journal:player-minimized";
const VIDEO_ID_PATTERN = /^[A-Za-z0-9_-]{11}$/;

let initialized = false;
let playerResizeObserver = null;

function syncPlayerLayout(player) {
    const root = document.documentElement;
    if (player.dataset.playerState === "empty") {
        root.style.setProperty("--persistent-player-height", "0px");
        root.style.setProperty("--persistent-player-map-offset", "0.75rem");
        return;
    }
    const playerRect = player.getBoundingClientRect();
    const mapWorkspace = document.querySelector(".map-workspace");
    const mapOffset = mapWorkspace
        ? Math.max(12, mapWorkspace.getBoundingClientRect().bottom - playerRect.top + 16)
        : 12;
    root.style.setProperty("--persistent-player-height", `${playerRect.height}px`);
    root.style.setProperty("--persistent-player-map-offset", `${mapOffset}px`);
}

function setMinimized(player, minimized) {
    player.classList.toggle("is-minimized", minimized);
    player.querySelector("[data-player-minimize]")?.setAttribute("aria-label", minimized ? "Restore video player" : "Minimize video player");
    const minimize = player.querySelector("[data-player-minimize]");
    if (minimize) {
        minimize.title = minimized ? "Restore" : "Minimize";
        const minimizeIcon = minimize.querySelector("[data-player-minimize-icon]");
        const restoreIcon = minimize.querySelector("[data-player-restore-icon]");
        if (minimizeIcon) minimizeIcon.hidden = minimized;
        if (restoreIcon) restoreIcon.hidden = !minimized;
    }
    const toggle = document.querySelector("[data-player-toggle]");
    toggle?.setAttribute("aria-expanded", String(!minimized));
    toggle?.toggleAttribute("hidden", !minimized);

    try {
        localStorage.setItem(MINIMIZED_KEY, String(minimized));
    } catch (error) {
        // Player controls remain usable when storage is unavailable.
    }
    syncPlayerLayout(player);
}

function clearPlayer(player) {
    player.dataset.playerState = "empty";
    player.classList.remove("is-minimized");
    player.querySelector("[data-player-stage]")?.replaceChildren();
    player.querySelector("[data-player-actions]")?.setAttribute("hidden", "");
    player.querySelector("[data-player-title]").textContent = "No video selected";
    player.querySelector("[data-player-channel]").textContent = "";
    const toggle = document.querySelector("[data-player-toggle]");
    toggle?.setAttribute("hidden", "");
    toggle?.setAttribute("aria-expanded", "false");
    syncPlayerLayout(player);
}

function playVideo(player, detail) {
    const videoId = detail?.videoId;
    if (!VIDEO_ID_PATTERN.test(videoId ?? "")) {
        console.error("World Journal rejected an invalid YouTube video ID");
        return;
    }
    const startSeconds = detail.startSeconds ?? 0;
    if (!Number.isSafeInteger(startSeconds) || startSeconds < 0 || startSeconds > 2147483647) {
        console.error("World Journal rejected an invalid video start time");
        return;
    }
    const title = typeof detail.title === "string" && detail.title.trim() ? detail.title.trim() : "YouTube video";
    const channel = typeof detail.channel === "string" ? detail.channel.trim() : "";
    const iframe = document.createElement("iframe");
    iframe.src = `https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1${startSeconds ? `&start=${startSeconds}` : ""}`;
    iframe.title = `${title} on YouTube`;
    iframe.allow = "autoplay; encrypted-media; picture-in-picture";
    iframe.referrerPolicy = "strict-origin-when-cross-origin";
    iframe.allowFullscreen = true;

    player.querySelector("[data-player-stage]").replaceChildren(iframe);
    player.querySelector("[data-player-title]").textContent = title;
    player.querySelector("[data-player-channel]").textContent = channel;
    player.querySelector("[data-player-actions]")?.removeAttribute("hidden");
    player.dataset.playerState = "playing";
    setMinimized(player, false);
}

export function initializePlayer() {
    if (initialized) {
        return;
    }
    const player = document.querySelector("#persistent-player");
    if (!player) {
        return;
    }
    initialized = true;

    let minimized = false;
    try {
        minimized = localStorage.getItem(MINIMIZED_KEY) === "true";
    } catch (error) {
        minimized = false;
    }
    setMinimized(player, minimized);

    player.querySelector("[data-player-minimize]")?.addEventListener("click", () => {
        setMinimized(player, !player.classList.contains("is-minimized"));
    });
    document.querySelector("[data-player-toggle]")?.addEventListener("click", () => setMinimized(player, false));
    player.querySelector("[data-player-close]")?.addEventListener("click", () => clearPlayer(player));
    document.addEventListener("world-journal:play-video", (event) => playVideo(player, event.detail));
    document.addEventListener("world-journal:page-ready", () => requestAnimationFrame(() => syncPlayerLayout(player)));
    window.addEventListener("resize", () => syncPlayerLayout(player));
    playerResizeObserver = new ResizeObserver(() => syncPlayerLayout(player));
    playerResizeObserver.observe(player);
}