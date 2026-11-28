import { loadPlayerApi } from "../player.js";
import { randomId } from "../random_id.js";

const embeds = new Map();
const videoId = /^[A-Za-z0-9_-]{11}$/;
const maxStart = 2147483647;

function reference(value) {
    try {
        const url = new URL(value);
        if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) return null;
        const host = url.hostname.toLowerCase();
        const parts = url.pathname.replace(/^\/+|\/+$/g, "").split("/");
        let id;
        if (["youtu.be", "www.youtu.be"].includes(host) && parts.length === 1) id = parts[0];
        else if (["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com"].includes(host)) {
            if (url.pathname === "/watch") id = url.searchParams.get("v");
            else if (parts.length === 2 && ["shorts", "embed", "live"].includes(parts[0])) id = parts[1];
        }
        if (!videoId.test(id || "")) return null;
        const raw = url.searchParams.get("t") || url.searchParams.get("start") || "";
        const match = raw.match(/^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$/);
        const start = /^\d+$/.test(raw) ? Number(raw) : match ? Number(match[1] || 0) * 3600 + Number(match[2] || 0) * 60 + Number(match[3] || 0) : 0;
        return {id, start: Math.min(maxStart, start)};
    } catch { return null; }
}

function dispose(panel) {
    const record = embeds.get(panel);
    if (!record) return;
    embeds.delete(panel);
    record.player?.destroy();
    panel.querySelector("[data-journal-video-mount]").replaceChildren();
}

export function pauseJournalVideos(except = null) {
    for (const [panel, record] of embeds) {
        if (panel === except) continue;
        if (record.ready) record.player.pauseVideo();
        else record.frame.contentWindow?.postMessage(JSON.stringify({event: "command", func: "pauseVideo", args: []}), "https://www.youtube-nocookie.com");
    }
}

export function refreshJournalVideos(root = document) {
    for (const panel of embeds.keys()) if (!panel.isConnected) dispose(panel);
    for (const panel of root.querySelectorAll("[data-journal-video]")) {
        if (panel.closest("[data-editor-page][hidden]")) continue;
        if (panel.hasAttribute("data-editable-video")) {
            const fields = panel.closest("[data-content-fields]");
            const input = name => fields.querySelector(`[name="${name}"], [name$="-${name}"]`);
            const source = reference(input("source_url").value);
            panel.dataset.videoId = source?.id || "";
            const seconds = input("youtube_start_seconds").value;
            panel.dataset.videoStart = seconds === "" ? source?.start || 0 : Math.max(0, Math.min(maxStart, Number(seconds) || 0));
            panel.dataset.videoTitle = input("title").value || "YouTube video";
            panel.dataset.videoChannel = input("source_name").value || "YouTube";
        }
        const id = panel.dataset.videoId;
        panel.hidden = !videoId.test(id);
        if (panel.hidden) { dispose(panel); continue; }
        const start = Math.max(0, Math.min(maxStart, Number(panel.dataset.videoStart) || 0));
        panel.querySelector("[data-journal-video-link]").href = `https://www.youtube.com/watch?v=${id}&t=${start}s`;
        const key = `${id}:${start}`;
        const previous = embeds.get(panel);
        if (previous?.key === key) {
            previous.frame.title = panel.dataset.videoTitle;
            continue;
        }
        dispose(panel);
        const frame = document.createElement("iframe");
        frame.id = `journal-video-${randomId()}`;
        frame.title = panel.dataset.videoTitle || "YouTube video";
        frame.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
        frame.allowFullscreen = true;
        frame.loading = "lazy";
        frame.referrerPolicy = "strict-origin-when-cross-origin";
        const params = new URLSearchParams({enablejsapi: "1", origin: location.origin, rel: "0", start: String(start)});
        frame.src = `https://www.youtube-nocookie.com/embed/${id}?${params}`;
        panel.querySelector("[data-journal-video-mount]").append(frame);
        const record = {key, frame, player: null, ready: false};
        embeds.set(panel, record);
        loadPlayerApi().then(YT => {
            if (embeds.get(panel) !== record || !panel.isConnected) return;
            record.player = new YT.Player(frame, {events: {
                onReady: () => { record.ready = true; },
                onStateChange: event => {
                    if (event.data === 1 && embeds.get(panel) === record) pauseJournalVideos(panel);
                },
            }});
        }).catch(() => { /* The iframe's ordinary playback controls still work. */ });
    }
}

export function journalVideoDetails(button) {
    const panel = button.closest("[data-journal-video]");
    const data = panel?.dataset || button.dataset;
    const record = panel && embeds.get(panel);
    const current = record?.ready ? record.player.getCurrentTime() : NaN;
    return {videoId: data.videoId, title: data.videoTitle, channel: data.videoChannel,
        startSeconds: Number.isFinite(current) && current > 0 ? current : Number(data.videoStart || 0)};
}

export function clearJournalVideos() {
    for (const panel of embeds.keys()) dispose(panel);
}
