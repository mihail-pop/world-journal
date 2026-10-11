let registered = false;
const pendingPreviews = new Set();

function updatePositions(editor) {
    let position = 0;
    for (const card of editor.querySelectorAll("[data-journal-section]")) {
        const deleted = card.querySelector('[name$="-DELETE"]')?.checked;
        card.classList.toggle("is-deleted", Boolean(deleted));
        card.querySelector(".journal-section-deleted").hidden = !deleted;
        card.querySelector(".journal-section-fields").hidden = Boolean(deleted);
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
    const format = scope.querySelector('select[name$="body_format"]');
    if (format.value !== "markdown") return;
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
    const params = new URLSearchParams({body: scope.querySelector("[data-journal-body]").value, body_format: scope.querySelector('select[name$="body_format"]').value});
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
    document.addEventListener("click", event => {
        const play = event.target.closest("[data-journal-play]");
        if (play) {
            document.dispatchEvent(new CustomEvent("world-journal:play-video", {detail: {videoId: play.dataset.videoId, title: play.dataset.videoTitle, channel: play.dataset.videoChannel, startSeconds: Number(play.dataset.videoStart || 0)}}));
            return;
        }
        const editor = event.target.closest("[data-journal-editor]");
        if (!editor) return;
        if (event.target.closest("[data-journal-add-section]")) {
            event.preventDefault();
            addSection(editor);
        } else if (event.target.closest("[data-section-remove]")) {
            const card = event.target.closest("[data-journal-section]");
            const checkbox = card.querySelector('[name$="-DELETE"]');
            checkbox.checked = !checkbox.checked;
            updatePositions(editor);
        } else if (event.target.closest("[data-section-move]")) {
            const button = event.target.closest("[data-section-move]");
            const card = button.closest("[data-journal-section]");
            const sibling = button.dataset.sectionMove === "up" ? card.previousElementSibling : card.nextElementSibling;
            if (sibling) {
                if (button.dataset.sectionMove === "up") sibling.before(card);
                else sibling.after(card);
                updatePositions(editor);
            }
        } else if (event.target.closest("[data-journal-format]")) {
            formatBody(event.target.closest("[data-journal-format]"));
        } else if (event.target.closest("[data-journal-preview]")) {
            previewBody(event.target.closest("[data-journal-preview]"));
        }
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
        if (editor) updatePositions(editor);
    });
    document.addEventListener("world-journal:page-cleanup", () => {
        for (const abort of pendingPreviews) abort.abort();
        pendingPreviews.clear();
    });
}
