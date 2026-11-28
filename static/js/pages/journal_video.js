import { loadPlayerApi } from "../player.js";
import { randomId } from "../random_id.js";

const embeds = new Map();
const pageActions = new WeakMap();
const videoId = /^[A-Za-z0-9_-]{11}$/;
const maxStart = 2147483647;
const pageSelector = "[data-journal-video-page], [data-editor-page]";
const youtubeUrl = /(?<![\w./@-])(?:https?:\/\/)?(?:(?:www|m|music)\.)?(?:youtube\.com|youtube-nocookie\.com|youtu\.be)\/[^\s<>]+/gi;

function reference(value) {
    value = value.trim();
    if (!value || value.length > 2048) return null;
    try {
        const url = new URL(/^[\w+.-]+:\/\//.test(value) ? value : `https://${value}`);
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

function inlineReferences(text, href) {
    if (href) {
        const source = reference(href);
        return source ? [{...source, from: 0, to: text.length, title: reference(text) ? "YouTube video" : text}] : [];
    }
    const links = [];
    for (const match of text.matchAll(youtubeUrl)) {
        const url = match[0].replace(/[.,;:!?\])}]+$/, "");
        const source = reference(url);
        if (source) links.push({...source, from: match.index, to: match.index + url.length, title: "YouTube video"});
    }
    return links;
}

function inlinePanel(source, selectLink) {
    const panel = document.createElement("span");
    panel.className = "journal-inline-video";
    Object.assign(panel.dataset, {journalVideo: "", videoId: source.id, videoTitle: source.title || "YouTube video",
        videoChannel: "YouTube", videoStart: source.start});
    const mount = document.createElement("span");
    mount.className = "journal-video-mount";
    panel.append(mount);
    if (!selectLink) {
        mount.dataset.journalVideoMount = "";
        return panel;
    }
    const thumbnail = document.createElement("button");
    thumbnail.type = "button";
    thumbnail.className = "journal-video-thumbnail";
    thumbnail.setAttribute("aria-label", "Select video link");
    const image = document.createElement("img");
    image.dataset.journalVideoThumbnail = "";
    image.alt = source.title;
    image.loading = "lazy";
    image.decoding = "async";
    thumbnail.append(image);
    thumbnail.addEventListener("click", selectLink);
    mount.append(thumbnail);
    const actions = document.createElement("span");
    actions.className = "journal-embedded-video-actions";
    actions.dataset.journalVideoActions = "";
    panel.append(actions);
    return panel;
}

function previewInlineVideos(body) {
    const links = body.querySelectorAll("a[href]");
    for (const link of links) {
        if (!body.contains(link) || link.closest("code, pre")) continue;
        const href = link.getAttribute("href");
        const [source] = inlineReferences(link.textContent, href);
        if (!source) continue;
        // A linked phrase can span several adjacent text marks in rich text.
        while (link.nextSibling?.nodeName === "A" && link.nextSibling.getAttribute("href") === href) {
            link.nextSibling.remove();
        }
        link.replaceWith(inlinePanel(source));
    }
    const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
    const replacements = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (node.parentElement.closest("a, code, pre")) continue;
        const sources = inlineReferences(node.data);
        if (sources.length) replacements.push([node, sources]);
    }
    for (const [node, sources] of replacements) {
        const fragment = document.createDocumentFragment();
        let start = 0;
        for (const source of sources) {
            fragment.append(node.data.slice(start, source.from), inlinePanel(source));
            start = source.to;
        }
        fragment.append(node.data.slice(start));
        node.replaceWith(fragment);
    }
}

function documentVideoLinks(doc) {
    const links = [];
    doc.descendants((block, pos) => {
        if (!block.isTextblock) return;
        if (block.type.spec.code) return false;
        let run;
        const flush = () => {
            if (!run) return;
            for (const source of inlineReferences(run.text, run.href)) {
                links.push({...source, from: run.pos + source.from, to: run.pos + source.to});
            }
            run = null;
        };
        block.forEach((node, offset) => {
            if (!node.isText || node.marks.some(mark => mark.type.spec.code)) { flush(); return; }
            const href = node.marks.find(mark => mark.type.name === "link")?.attrs.href;
            if (run && run.href !== href) flush();
            run ||= {pos: pos + 1 + offset, text: "", href};
            run.text += node.text;
        });
        flush();
        return false;
    });
    return links;
}

function movePastThumbnail(editor, direction, links, Selection) {
    const {view, state: {doc, selection}} = editor;
    const {$from} = selection;
    if (!editor.isEditable || !$from.parent.isTextblock || !links.length) return false;
    if (!selection.empty && !links.some(video => video.from === selection.from && video.to === selection.to)) return false;

    const isVideoLine = position => position.parent.isTextblock && links.some(video =>
        video.from === position.start() && video.to === position.end());
    let crossedVideo = isVideoLine($from) || (direction > 0 && links.some(video =>
        video.to === selection.to && video.to === $from.end()));
    if (!crossedVideo && (!selection.empty || !view.endOfTextblock(direction > 0 ? "down" : "up"))) return false;

    const nextLine = position => Selection.findFrom(doc.resolve(direction > 0 ? position.after() : position.before()), direction);
    let target = nextLine($from);
    while (target && isVideoLine(target.$from)) {
        crossedVideo = true;
        target = nextLine(target.$from);
    }
    if (!crossedVideo) return false;
    if (target) {
        view.dispatch(view.state.tr.setSelection(target).scrollIntoView());
    } else if (direction > 0) {
        // Create a writing line only when moving down past the last video.
        return editor.commands.insertContentAt(doc.content.size, {type: "paragraph"});
    }
    return true;
}

export function journalVideoThumbnails({Extension, Plugin, Selection, Decoration, DecorationSet}) {
    const documentLinks = new WeakMap();
    const linksFor = doc => {
        if (!documentLinks.has(doc)) documentLinks.set(doc, documentVideoLinks(doc));
        return documentLinks.get(doc);
    };
    return Extension.create({
        name: "journalVideoThumbnails",
        addKeyboardShortcuts() {
            const {editor} = this;
            return {
                ArrowDown: () => movePastThumbnail(editor, 1, linksFor(editor.state.doc), Selection),
                ArrowUp: () => movePastThumbnail(editor, -1, linksFor(editor.state.doc), Selection),
            };
        },
        addProseMirrorPlugins() {
            const {editor} = this;
            return [new Plugin({props: {
                decorations({doc, selection}) {
                    const decorations = [];
                    const occurrences = new Map();
                    for (const source of linksFor(doc)) {
                        const {from, to, id, start, title} = source;
                        const key = `${id}:${start}:${to - from}:${title}`;
                        const occurrence = occurrences.get(key) || 0;
                        occurrences.set(key, occurrence + 1);
                        if (selection.from >= to || selection.to <= from) {
                            decorations.push(Decoration.inline(from, to, {class: "journal-video-url"}));
                        }
                        decorations.push(Decoration.widget(to, (_view, getPos) => inlinePanel(source, () => {
                            const end = getPos();
                            editor.chain().focus().setTextSelection({from: end - (to - from), to: end}).run();
                        }), {key: `${occurrence}:${key}`, marks: [], stopEvent: () => true}));
                    }
                    return DecorationSet.create(doc, decorations);
                },
            }})];
        },
    });
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

function pageVideos(page) {
    return [...page.querySelectorAll("[data-journal-video]")]
        .filter(panel => !panel.closest("[hidden]") && videoId.test(panel.dataset.videoId));
}

function syncVideoAction(page) {
    const first = pageVideos(page)[0];
    const target = (first?.closest("[data-journal-reading-section]") || first)?.querySelector("[data-journal-video-actions]");
    let button = pageActions.get(page);
    if (!target) { button?.remove(); return; }
    if (!button) {
        button = document.createElement("button");
        button.className = "journal-button";
        button.type = "button";
        button.dataset.journalPlay = "";
        button.textContent = "Open in player";
        pageActions.set(page, button);
    }
    if (button.parentElement !== target) target.prepend(button);
}

export function refreshJournalVideos(root = document) {
    for (const panel of embeds.keys()) if (!panel.isConnected) dispose(panel);
    for (const body of root.querySelectorAll("[data-journal-video-page] .journal-rendered")) previewInlineVideos(body);
    for (const panel of root.querySelectorAll("[data-journal-video]")) {
        if (panel.parentElement.closest("[hidden]")) continue;
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
        const thumbnail = panel.querySelector("[data-journal-video-thumbnail]");
        if (thumbnail) {
            const src = `https://i.ytimg.com/vi/${id}/hqdefault.jpg`;
            if (thumbnail.getAttribute("src") !== src) thumbnail.src = src;
            continue;
        }
        const start = Math.max(0, Math.min(maxStart, Number(panel.dataset.videoStart) || 0));
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
    const pages = root.matches?.(pageSelector) ? [root] : root.querySelectorAll(pageSelector);
    for (const page of pages) syncVideoAction(page);
}

export function journalVideoQueue(button, entryEditUrl) {
    const page = button.closest(pageSelector);
    if (!page) return [];
    const queue = new Map();
    for (const panel of pageVideos(page)) {
        const {videoId, videoTitle, videoChannel, videoStart} = panel.dataset;
        if (queue.has(videoId)) continue;
        const record = embeds.get(panel);
        const current = record?.ready ? record.player.getCurrentTime() : NaN;
        queue.set(videoId, {videoId, title: videoTitle, channel: videoChannel,
            startSeconds: Number.isFinite(current) && current > 0 ? current : Number(videoStart || 0),
            saveUrl: panel.hasAttribute("data-journal-main-video") ? page.dataset.journalVideoPage || entryEditUrl : undefined});
    }
    return [...queue.values()];
}

export function clearJournalVideos() {
    for (const panel of embeds.keys()) dispose(panel);
}
