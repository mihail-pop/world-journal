import { registerJournalAutosave } from "./journal_autosave.js";

let registered = false;
const pendingPreviews = new Set();

function updatePositions(editor) {
    let position = 0;
    for (const card of editor.querySelectorAll("[data-journal-section]")) {
        const deleted = card.querySelector('[name$="-DELETE"]')?.checked;
        card.classList.toggle("is-deleted", Boolean(deleted));
        card.querySelector(".journal-section-deleted").hidden = !deleted;
        const fields = card.querySelector(".journal-section-fields");
        fields.hidden = Boolean(deleted);
        for (const input of fields.querySelectorAll("input, select, textarea")) {
            // Deleted sections must not fail native validation while hidden.
            if (deleted && !input.disabled) {
                input.dataset.sectionDisabled = "true";
                input.disabled = true;
            } else if (!deleted && input.dataset.sectionDisabled) {
                input.disabled = false;
                delete input.dataset.sectionDisabled;
            }
        }
        const input = card.querySelector('[name$="-position"]');
        if (input && !deleted) input.value = position++;
    }
}

function addSection(editor) {
    const total = editor.querySelector('[name="sections-TOTAL_FORMS"]');
    const index = Number(total.value);
    if (index >= 200) return;
    const template = editor.querySelector("[data-journal-section-template]");
    const container = editor.querySelector("[data-journal-sections]");
    container.insertAdjacentHTML("beforeend", template.innerHTML.replaceAll("__prefix__", String(index)));
    total.value = index + 1;
    updatePositions(editor);
    container.lastElementChild.querySelector('input[name$="-title"]')?.focus();
}

function formatBody(button) {
    const scope = button.closest("[data-content-fields]");
    const body = scope.querySelector("[data-journal-body]");
    const start = body.selectionStart;
    const end = body.selectionEnd;
    const selected = body.value.slice(start, end) || "text";
    const formats = {bold: ["**", "**"], italic: ["*", "*"], heading: ["\n## ", "\n"], list: ["\n- ", "\n"], quote: ["\n> ", "\n"], code: ["`", "`"]};
    const [prefix, suffix] = formats[button.dataset.journalFormat];
    body.setRangeText(prefix + selected + suffix, start, end, "select");
    body.focus();
    body.dispatchEvent(new Event("input", {bubbles: true}));
}

async function previewBody(button) {
    const scope = button.closest("[data-content-fields]");
    const form = button.closest("form");
    const output = scope.querySelector("[data-journal-preview-output]");
    const abort = new AbortController();
    pendingPreviews.add(abort);
    button.disabled = true;
    output.hidden = false;
    output.textContent = "Preparing preview…";
    const params = new URLSearchParams({body: scope.querySelector("[data-journal-body]").value, body_format: "markdown"});
    try {
        const response = await fetch(form.dataset.previewUrl, {method: "POST", headers: {"X-CSRFToken": form.querySelector('[name="csrfmiddlewaretoken"]').value}, body: params, signal: abort.signal});
        if (!response.ok) throw new Error("Preview unavailable");
        const html = await response.text();
        if (output.isConnected) output.innerHTML = html || "<p>Nothing to preview yet.</p>";
    } catch (error) {
        if (error.name !== "AbortError" && output.isConnected) output.textContent = "Preview could not be loaded. Your text is still in the editor.";
    } finally {
        pendingPreviews.delete(abort);
        button.disabled = false;
    }
}

export function registerJournalPage() {
    if (registered) return;
    registered = true;
    registerJournalAutosave();
    function openCard(event) {
        const card = event.target.closest("[data-journal-entry-card]");
        if (!card || event.target.closest("a, button, input, textarea, select, summary, label")) return;
        if (event.type === "click" && !window.getSelection()?.isCollapsed) return;
        if (event.type === "keydown" && (event.target !== card || !["Enter", " "].includes(event.key))) return;
        if (event.type === "click" && event.button !== 0) return;
        const link = card.querySelector("[data-entry-link]");
        event.preventDefault();
        if (event.ctrlKey || event.metaKey) window.open(link.href, "_blank", "noopener,noreferrer");
        else link.click();
    }
    document.addEventListener("keydown", openCard);
    document.addEventListener("click", openCard);
    document.addEventListener("world-journal:prepare-save", event => updatePositions(event.target));
    document.addEventListener("click", event => {
        const play = event.target.closest("[data-journal-play]");
        if (play) {
            const entryPath = location.pathname.match(/^\/journal\/([a-f0-9-]{36})\//);
            document.dispatchEvent(new CustomEvent("world-journal:play-video", {detail: {videoId: play.dataset.videoId, title: play.dataset.videoTitle, channel: play.dataset.videoChannel, startSeconds: Number(play.dataset.videoStart || 0), saveUrl: entryPath ? `/journal/${entryPath[1]}/edit/` : undefined}}));
            return;
        }
        const editor = event.target.closest("[data-journal-editor]");
        if (!editor) return;
        if (event.target.closest("[data-journal-add-section]")) {
            event.preventDefault();
            addSection(editor);
            editor.dispatchEvent(new Event("world-journal:editor-changed"));
        } else if (event.target.closest("[data-section-remove]")) {
            const card = event.target.closest("[data-journal-section]");
            const checkbox = card.querySelector('[name$="-DELETE"]');
            checkbox.checked = !checkbox.checked;
            updatePositions(editor);
            editor.dispatchEvent(new Event("world-journal:editor-changed"));
        } else if (event.target.closest("[data-section-move]")) {
            const button = event.target.closest("[data-section-move]");
            const card = button.closest("[data-journal-section]");
            const sibling = button.dataset.sectionMove === "up" ? card.previousElementSibling : card.nextElementSibling;
            if (sibling) {
                if (button.dataset.sectionMove === "up") sibling.before(card);
                else sibling.after(card);
                updatePositions(editor);
                editor.dispatchEvent(new Event("world-journal:editor-changed"));
            }
        } else if (event.target.closest("[data-journal-format]")) {
            formatBody(event.target.closest("[data-journal-format]"));
        } else if (event.target.closest("[data-journal-preview]")) {
            previewBody(event.target.closest("[data-journal-preview]"));
        }
    });
    document.addEventListener("invalid", event => {
        // Browser validation must be able to focus fields inside folded panels.
        if (!event.target.closest("[data-journal-editor]")) return;
        for (let parent = event.target.parentElement; parent; parent = parent.parentElement) {
            if (parent.matches("details")) parent.open = true;
        }
    }, true);
    document.addEventListener("input", event => {
        if (!event.target.matches('input[name$="-title"]')) return;
        const caption = event.target.closest("[data-journal-section]")?.querySelector("[data-section-caption]");
        if (caption) caption.textContent = event.target.value.trim() || "Untitled section";
    });
    document.addEventListener("change", event => {
        if (event.target.matches('[name$="-DELETE"]')) {
            const editor = event.target.closest("[data-journal-editor]");
            if (editor) updatePositions(editor);
        }
    });
    document.addEventListener("submit", event => {
        if (event.target.matches("[data-journal-editor]")) updatePositions(event.target);
    }, true);
    document.addEventListener("world-journal:page-ready", () => {
        const editor = document.querySelector("[data-journal-editor]");
        if (editor) {
            updatePositions(editor);
        }
        const collections = document.querySelector(".journal-collections");
        if (collections && !collections.dataset.initialized) {
            collections.open = !window.matchMedia("(max-width: 46rem)").matches;
            collections.dataset.initialized = "true";
        }
    });
    document.addEventListener("world-journal:page-cleanup", () => {
        for (const abort of pendingPreviews) abort.abort();
        pendingPreviews.clear();
    });
}
