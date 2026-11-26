import { registerJournalAutosave } from "./journal_autosave.js";
import { registerJournalList } from "./journal_list.js";
import { registerInfiniteScroll } from "../infinite_scroll.js";
import { registerJournalRichtext, refreshRichEditors, focusRichEditor } from "./journal_richtext.js";
import { refreshJournalVideos, pauseJournalVideos, journalVideoDetails, clearJournalVideos } from "./journal_video.js";

let registered = false;
const eventDates = new WeakMap();

function syncEventDate(editor, changed) {
    const field = editor.elements.namedItem("event_date");
    const release = editor.elements.namedItem("source_published_at");
    if (!field || !release) return;
    if (!eventDates.has(editor)) eventDates.set(editor, {
        automatic: new URL(editor.action, location.href).pathname === "/journal/new/",
        value: field.value,
    });
    const state = eventDates.get(editor);
    if (changed === field) state.automatic = false;
    if (state.automatic && (!field.value || field.value === state.value)) {
        const date = release.value.slice(0, 10);
        if (/^\d{4}-\d{2}-\d{2}$/.test(date)) {
            field.value = date;
            state.value = date;
        }
    }
}

function activeContent(editor) {
    const page = editor.querySelector(`[data-editor-page="${CSS.escape(editor.dataset.activePage || "main")}"]`);
    return page?.querySelector("[data-content-fields]");
}

function setActivePage(editor, key, focus = false) {
    if (!editor.querySelector(`[data-editor-page="${CSS.escape(key)}"]`)) key = "main";
    if (editor.dataset.activePage !== key) pauseJournalVideos();
    editor.dataset.activePage = key;
    for (const page of editor.querySelectorAll("[data-editor-page]")) page.hidden = page.dataset.editorPage !== key;
    for (const button of editor.querySelectorAll("[data-journal-page]")) {
        if (button.dataset.journalPage === key) button.setAttribute("aria-current", "page");
        else button.removeAttribute("aria-current");
    }
    refreshRichEditors(editor);
    refreshJournalVideos(editor);
    if (focus) focusRichEditor(activeContent(editor)?.querySelector("[data-journal-body]"));
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
        button.setAttribute("aria-label", item.deleted ? `${item.title} (marked for removal)` : item.title);
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

function revealField(editor, field) {
    const page = field.closest("[data-editor-page]");
    if (page) setActivePage(editor, page.dataset.editorPage);
    if (field.matches("[data-journal-body]")) focusRichEditor(field);
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
    registerJournalRichtext();
    registerJournalAutosave();
    registerJournalList();
    document.addEventListener("world-journal:play-video", () => pauseJournalVideos());
    document.addEventListener("world-journal:page-cleanup", clearJournalVideos);
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
            const details = journalVideoDetails(play);
            pauseJournalVideos();
            document.dispatchEvent(new CustomEvent("world-journal:play-video", {detail: {...details, saveUrl: entryPath ? `/journal/${entryPath[1]}/edit/` : undefined}}));
            return;
        }
        const editor = event.target.closest("[data-journal-editor]");
        if (!editor) return;
        const flag = event.target.closest("[data-journal-flag-toggle]");
        if (flag) {
            const input = editor.elements.namedItem(flag.dataset.journalFlagToggle);
            input.checked = !input.checked;
            flag.setAttribute("aria-pressed", String(input.checked));
            input.dispatchEvent(new Event("change", {bubbles: true}));
            return;
        }
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
        }
    });
    document.addEventListener("invalid", event => {
        const editor = event.target.closest("[data-journal-editor]");
        if (editor) revealField(editor, event.target);
    }, true);
    document.addEventListener("input", event => {
        const editor = event.target.closest("[data-journal-editor]");
        if (!editor) return;
        syncEventDate(editor, event.target);
        if (event.target.matches('input[name$="-title"]')) syncSectionNav(editor);
        if (event.target.matches('[name$="source_url"], [name$="youtube_start_seconds"], [name$="title"], [name$="source_name"]')) refreshJournalVideos(editor);
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
            syncEventDate(editor);
            updatePositions(editor);
            const invalid = editor.querySelector(".errorlist li")?.closest("[data-editor-page]");
            if (invalid) setActivePage(editor, invalid.dataset.editorPage);
        }
        refreshJournalVideos();
    });
}
