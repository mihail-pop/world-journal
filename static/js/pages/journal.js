import { registerJournalAutosave } from "./journal_autosave.js";
import { notify } from "../notifications.js";
import { registerInfiniteScroll } from "../infinite_scroll.js";

let registered = false;
const pendingPreviews = new Set();
const previewRequests = new WeakMap();

function activeContent(editor) {
    const page = editor.querySelector(`[data-editor-page="${CSS.escape(editor.dataset.activePage || "main")}"]`);
    return page?.querySelector("[data-content-fields]");
}

function resizeBody(body) {
    if (!body || !body.offsetParent) return;
    body.style.height = "auto";
    body.style.height = `${body.scrollHeight}px`;
}

function syncToolbar(editor) {
    const scope = activeContent(editor);
    const previewing = scope?.dataset.preview === "true";
    editor.querySelector("[data-journal-preview]").setAttribute("aria-pressed", String(previewing));
    for (const button of editor.querySelectorAll("[data-journal-format]")) button.disabled = previewing;
}

function setActivePage(editor, key, focus = false) {
    if (!editor.querySelector(`[data-editor-page="${CSS.escape(key)}"]`)) key = "main";
    editor.dataset.activePage = key;
    for (const page of editor.querySelectorAll("[data-editor-page]")) page.hidden = page.dataset.editorPage !== key;
    for (const button of editor.querySelectorAll("[data-journal-page]")) {
        if (button.dataset.journalPage === key) button.setAttribute("aria-current", "page");
        else button.removeAttribute("aria-current");
    }
    syncToolbar(editor);
    const body = activeContent(editor)?.querySelector("[data-journal-body]");
    resizeBody(body);
    if (focus) body?.focus({preventScroll: true});
}

function syncSectionNav(editor) {
    const nav = editor.querySelector("[data-journal-section-nav]");
    const focusedKey = nav.contains(document.activeElement) ? document.activeElement.dataset.journalPage : null;
    const items = [{key: "main", title: "Main text"}];
    for (const [index, section] of [...editor.querySelectorAll("[data-journal-section]")].entries()) {
        items.push({key: section.dataset.editorPage,
            title: section.querySelector('input[name$="-title"]').value.trim() || `Section ${index + 1}`,
            deleted: section.querySelector('[name$="-DELETE"]').checked});
    }
    nav.replaceChildren(...items.map(item => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.journalPage = item.key;
        button.textContent = item.title;
        button.title = item.deleted ? `${item.title} (marked for removal)` : item.title;
        button.classList.toggle("is-deleted", Boolean(item.deleted));
        return button;
    }));
    setActivePage(editor, editor.dataset.activePage || "main");
    if (focusedKey) nav.querySelector(`[data-journal-page="${CSS.escape(focusedKey)}"]`)?.focus({preventScroll: true});
}

function updatePositions(editor) {
    let position = 0;
    for (const card of editor.querySelectorAll("[data-journal-section]")) {
        const deleted = card.querySelector('[name$="-DELETE"]').checked;
        card.classList.toggle("is-deleted", deleted);
        card.querySelector(".journal-section-deleted").hidden = !deleted;
        const fields = card.querySelector(".journal-section-fields");
        fields.hidden = deleted;
        for (const input of fields.querySelectorAll("input, select, textarea")) {
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
    syncSectionNav(editor);
}

function addSection(editor) {
    const total = editor.querySelector('[name="sections-TOTAL_FORMS"]');
    const index = Number(total.value);
    if (index >= 200) return;
    editor.querySelector("[data-journal-sections]").insertAdjacentHTML("beforeend",
        editor.querySelector("[data-journal-section-template]").innerHTML.replaceAll("__prefix__", String(index)));
    total.value = index + 1;
    updatePositions(editor);
    setActivePage(editor, `sections-${index}`);
    editor.elements.namedItem(`sections-${index}-title`)?.focus({preventScroll: true});
}

function setPreview(editor, scope, show) {
    scope.dataset.preview = String(show);
    const body = scope.querySelector("[data-journal-body]");
    const output = scope.querySelector("[data-journal-preview-output]");
    if (show) output.style.minHeight = `${body.offsetHeight}px`;
    scope.querySelector("[data-journal-body-field]").hidden = show;
    output.hidden = !show;
    if (activeContent(editor) === scope) syncToolbar(editor);
    if (!show) resizeBody(body);
}

function formatBody(button) {
    const editor = button.closest("[data-journal-editor]");
    const scope = activeContent(editor);
    const body = scope.querySelector("[data-journal-body]");
    const start = body.selectionStart, end = body.selectionEnd;
    const selected = body.value.slice(start, end) || "text";
    const formats = {bold: ["**", "**"], italic: ["*", "*"], heading: ["\n## ", "\n"], list: ["\n- ", "\n"], quote: ["\n> ", "\n"], code: ["`", "`"]};
    const [prefix, suffix] = formats[button.dataset.journalFormat];
    body.setRangeText(prefix + selected + suffix, start, end, "select");
    body.focus({preventScroll: true});
    body.dispatchEvent(new Event("input", {bubbles: true}));
}

async function previewBody(button) {
    const editor = button.closest("[data-journal-editor]");
    const scope = activeContent(editor);
    const pending = previewRequests.get(scope);
    if (scope.dataset.preview === "true" || pending) {
        pending?.abort();
        previewRequests.delete(scope);
        button.removeAttribute("aria-busy");
        setPreview(editor, scope, false);
        scope.querySelector("[data-journal-body]").focus({preventScroll: true});
        return;
    }
    const output = scope.querySelector("[data-journal-preview-output]");
    const text = scope.querySelector("[data-journal-body]").value;
    const abort = new AbortController();
    pendingPreviews.add(abort);
    previewRequests.set(scope, abort);
    button.setAttribute("aria-busy", "true");
    try {
        const response = await fetch(editor.dataset.previewUrl, {method: "POST", headers: {"X-CSRFToken": editor.querySelector('[name="csrfmiddlewaretoken"]').value},
            body: new URLSearchParams({body: text, body_format: "markdown"}), signal: abort.signal});
        if (!response.ok) throw new Error("Preview unavailable");
        const html = await response.text();
        if (previewRequests.get(scope) !== abort || !scope.isConnected || scope.querySelector("[data-journal-body]").value !== text) return;
        output.innerHTML = html;
        setPreview(editor, scope, true);
    } catch (error) {
        if (error.name !== "AbortError" && scope.isConnected) notify({id: "journal-preview", kind: "error", title: "Preview unavailable", message: "Your text is still in the editor. Try Preview again."});
    } finally {
        pendingPreviews.delete(abort);
        if (previewRequests.get(scope) === abort) previewRequests.delete(scope);
        button.removeAttribute("aria-busy");
    }
}

function revealField(editor, field) {
    const page = field.closest("[data-editor-page]");
    if (page) setActivePage(editor, page.dataset.editorPage);
    const scope = field.closest("[data-content-fields]");
    if (scope && field.matches("[data-journal-body]")) setPreview(editor, scope, false);
    for (let parent = field.parentElement; parent; parent = parent.parentElement) if (parent.matches("details")) parent.open = true;
}

function showFieldErrors(editor, {errors = {}, focus = false}) {
    for (const error of editor.querySelectorAll(".errorlist")) error.remove();
    for (const field of editor.querySelectorAll('[aria-invalid="true"]')) {
        field.removeAttribute("aria-invalid");
        delete field.dataset.journalInvalid;
    }
    let first;
    for (const [name, messages] of Object.entries(errors)) {
        const field = editor.elements.namedItem(name);
        if (!(field instanceof HTMLElement)) continue;
        field.setAttribute("aria-invalid", "true");
        field.dataset.journalInvalid = "true";
        const list = document.createElement("ul");
        list.className = "errorlist";
        list.dataset.journalValidation = "true";
        for (const message of messages) {
            const item = document.createElement("li");
            item.textContent = message;
            list.append(item);
        }
        (field.closest(".journal-field") || field.parentElement).append(list);
        first ||= field;
    }
    if (first && focus && editor.isConnected) {
        revealField(editor, first);
        first.focus({preventScroll: true});
        first.closest(".journal-field")?.scrollIntoView({block: "nearest", behavior: "smooth"});
    }
}

export function registerJournalPage() {
    if (registered) return;
    registered = true;
    registerInfiniteScroll({
        prefix: "journal",
        header: "X-Journal-Paging",
        changedMessage: "Your journal has changed. Refresh these results to continue.",
        reloadCollection: "[data-journal-collection]",
        reloadRoot: "[data-journal-list]",
        reloadForm: ".journal-search-form",
    });
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
    document.addEventListener("world-journal:validation-errors", event => showFieldErrors(event.target, event.detail));
    document.addEventListener("world-journal:sections-saved", event => updatePositions(event.target));
    document.addEventListener("click", event => {
        const play = event.target.closest("[data-journal-play]");
        if (play) {
            const entryPath = location.pathname.match(/^\/journal\/([a-f0-9-]{36})\//);
            document.dispatchEvent(new CustomEvent("world-journal:play-video", {detail: {videoId: play.dataset.videoId, title: play.dataset.videoTitle, channel: play.dataset.videoChannel, startSeconds: Number(play.dataset.videoStart || 0), saveUrl: entryPath ? `/journal/${entryPath[1]}/edit/` : undefined}}));
            return;
        }
        const editor = event.target.closest("[data-journal-editor]");
        if (!editor) return;
        const pageButton = event.target.closest("[data-journal-page]");
        if (pageButton) setActivePage(editor, pageButton.dataset.journalPage);
        else if (event.target.closest("[data-journal-add-section]")) {
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
            const cards = [...editor.querySelectorAll("[data-journal-section]")];
            const index = cards.indexOf(card);
            const sibling = cards[index + (button.dataset.sectionMove === "up" ? -1 : 1)];
            if (sibling) {
                if (button.dataset.sectionMove === "up") sibling.before(card);
                else sibling.after(card);
                updatePositions(editor);
                editor.dispatchEvent(new Event("world-journal:editor-changed"));
            }
        } else if (event.target.closest("[data-journal-format]")) formatBody(event.target.closest("[data-journal-format]"));
        else if (event.target.closest("[data-journal-preview]")) void previewBody(event.target.closest("[data-journal-preview]"));
    });
    document.addEventListener("invalid", event => {
        const editor = event.target.closest("[data-journal-editor]");
        if (editor) revealField(editor, event.target);
    }, true);
    document.addEventListener("input", event => {
        const editor = event.target.closest("[data-journal-editor]");
        if (!editor) return;
        if (event.target.matches("[data-journal-body]")) resizeBody(event.target);
        if (event.target.matches('input[name$="-title"]')) syncSectionNav(editor);
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
            const invalid = editor.querySelector(".errorlist li")?.closest("[data-editor-page]");
            if (invalid) setActivePage(editor, invalid.dataset.editorPage);
        }
        const collections = document.querySelector(".journal-collections");
        if (collections && !collections.dataset.initialized) {
            collections.open = !window.matchMedia("(max-width: 46rem)").matches;
            collections.dataset.initialized = "true";
        }
    });
    window.addEventListener("resize", () => {
        const editor = document.querySelector("[data-journal-editor]");
        if (editor) resizeBody(activeContent(editor)?.querySelector("[data-journal-body]"));
    });
    document.addEventListener("world-journal:page-cleanup", () => {
        for (const abort of pendingPreviews) abort.abort();
        pendingPreviews.clear();
    });
}
