import { notify } from "../notifications.js";
import { saveJournalEditor } from "./journal_autosave.js";

const controllers = new Map();
let library;
let registered = false;
const normalize = value => value.normalize("NFC").trim().replace(/\s+/g, " ").toLocaleLowerCase();
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

class JournalEditor {
    constructor(form, modules) {
        this.form = form;
        this.modules = modules;
        this.editors = new Map();
        this.toolbar = form.querySelector("[data-rich-toolbar]");
        this.aliases = JSON.parse(form.querySelector("#journal-country-aliases").textContent);
        form.journalPendingUploads = new Set();
        this.refresh();
        this.toolbar.inert = false;
    }

    active() {
        const page = this.form.dataset.activePage || "main";
        return [...this.editors.values()].find(editor => editor.view.dom.closest("[data-editor-page]")?.dataset.editorPage === page);
    }

    mount(field) {
        if (this.editors.has(field)) return;
        const {Editor, Extension, InputRule, StarterKit, Image, TableKit, TaskList, TaskItem, TextAlign, TextStyleKit, Placeholder} = this.modules;
        const root = field.parentElement.querySelector("[data-rich-editor]");
        root.replaceChildren();
        let content = root.dataset.legacyHtml || undefined;
        if (!content && field.value) content = JSON.parse(field.value);
        const LocalImage = Image.extend({
            addAttributes() {
                return {...this.parent?.(), attachmentId: {
                    default: null,
                    parseHTML: element => element.getAttribute("data-attachment-id"),
                    renderHTML: attrs => attrs.attachmentId ? {"data-attachment-id": attrs.attachmentId} : {},
                }, uploadId: {default: null, rendered: false}};
            },
            parseHTML() {
                return [{tag: "img[data-attachment-id]", getAttrs: element => uuid.test(element.getAttribute("data-attachment-id")) ? null : false}];
            },
            addInputRules() { return []; },
        });
        const aliases = this.aliases;
        const CountryLinks = Extension.create({
            name: "countryLinks",
            addInputRules() {
                return [new InputRule({find: /\[\[([^\]\n]+)\]\]$/, handler: ({state, range, match}) => {
                    const code = aliases[normalize(match[1])];
                    if (!code) return null;
                    const mark = state.schema.marks.link;
                    state.tr.insertText(match[1], range.from, range.to)
                        .addMark(range.from, range.from + match[1].length, mark.create({href: `/?country=${code}`, target: null}))
                        .removeStoredMark(mark);
                }})];
            },
        });
        const editor = new Editor({
            element: root,
            content,
            extensions: [
                StarterKit.configure({heading: {levels: [1, 2, 3]}, link: {
                    openOnClick: false, defaultProtocol: "https",
                    isAllowedUri: value => /^(https?:\/\/|\/(?!\/)|#)/i.test(value),
                }}),
                LocalImage.configure({resize: {enabled: true, alwaysPreserveAspectRatio: true, minWidth: 40, minHeight: 40}}),
                TableKit.configure({table: {resizable: true, allowTableNodeSelection: true}}),
                TaskList, TaskItem.configure({nested: true}), TextAlign.configure({types: ["heading", "paragraph"]}),
                TextStyleKit, Placeholder.configure({placeholder: "Start writing…"}), CountryLinks,
            ],
            editorProps: {
                attributes: {class: "journal-rich-editor", role: "textbox", "aria-multiline": "true", "aria-label": "Document body", spellcheck: "true"},
                handlePaste: (_view, event) => {
                    const files = [...(event.clipboardData?.files || [])];
                    if (!files.length) return false;
                    event.preventDefault();
                    this.insertImages(editor, files);
                    return true;
                },
                handleDrop: (view, event, _slice, moved) => {
                    const files = [...(event.dataTransfer?.files || [])];
                    if (!files.length || moved) return false;
                    event.preventDefault();
                    const point = view.posAtCoords({left: event.clientX, top: event.clientY});
                    if (point) editor.commands.setTextSelection(point.pos);
                    this.insertImages(editor, files);
                    return true;
                },
            },
            onUpdate: () => {
                this.syncField(field, editor);
                this.form.dispatchEvent(new Event("world-journal:editor-changed"));
                this.syncToolbar();
            },
            onSelectionUpdate: () => this.syncToolbar(),
            onTransaction: () => this.syncToolbar(),
        });
        this.editors.set(field, editor);
        this.syncField(field, editor);
    }

    syncField(field, editor) {
        field.value = editor.isEmpty ? "" : JSON.stringify(editor.getJSON());
    }

    refresh() {
        for (const [field, editor] of this.editors) {
            if (!this.form.contains(field)) { editor.destroy(); this.editors.delete(field); }
        }
        for (const field of this.form.querySelectorAll("[data-journal-body]")) this.mount(field);
        for (const [field, editor] of this.editors) editor.setEditable(!field.disabled, false);
        this.syncToolbar();
    }

    syncToolbar() {
        const editor = this.active();
        if (!editor || editor.isDestroyed) return;
        for (const button of this.toolbar.querySelectorAll("[data-rich-command]")) {
            const command = button.dataset.richCommand;
            if (button.hasAttribute("aria-pressed")) button.setAttribute("aria-pressed", String(editor.isActive(command)));
            if (["undo", "redo"].includes(command)) button.disabled = !editor.can()[command]();
            else if (button.hasAttribute("data-table-action")) button.disabled = !editor.isActive("table") || !editor.can()[command]();
            else button.disabled = !editor.isEditable;
        }
        this.toolbar.querySelector("[data-rich-style]").value = editor.isActive("heading") ? String(editor.getAttributes("heading").level) : "paragraph";
        const style = editor.getAttributes("textStyle");
        this.toolbar.querySelector("[data-rich-font]").value = style.fontFamily || "";
        this.toolbar.querySelector("[data-rich-size]").value = style.fontSize || "";
        if (/^#[a-f0-9]{6}$/i.test(style.color || "")) this.toolbar.querySelector("[data-rich-color]").value = style.color;
        if (/^#[a-f0-9]{6}$/i.test(style.backgroundColor || "")) this.toolbar.querySelector("[data-rich-highlight]").value = style.backgroundColor;
    }

    command(name) {
        const editor = this.active();
        if (!editor?.isEditable) return;
        const chain = editor.chain().focus();
        if (["bold", "italic", "underline", "strike", "bulletList", "orderedList", "taskList", "blockquote", "codeBlock"].includes(name)) {
            chain[`toggle${name[0].toUpperCase()}${name.slice(1)}`]().run();
        } else if (["left", "center", "right", "justify"].includes(name)) chain.setTextAlign(name).run();
        else if (name === "insertTable") chain.insertTable({rows: 3, cols: 3, withHeaderRow: true}).run();
        else if (name === "horizontalRule") chain.setHorizontalRule().run();
        else if (name === "clear") chain.unsetAllMarks().clearNodes().unsetTextAlign().run();
        else if (typeof chain[name] === "function") chain[name]().run();
        this.closeMenus();
    }

    closeMenus() {
        for (const menu of this.form.querySelectorAll("[data-rich-menu][open]")) menu.open = false;
    }

    openLink() {
        const editor = this.active();
        if (!editor?.isEditable) return;
        if (editor.isActive("link")) editor.commands.extendMarkRange("link");
        this.linkEditor = editor;
        this.linkRange = {from: editor.state.selection.from, to: editor.state.selection.to};
        const dialog = this.form.querySelector("[data-rich-link-dialog]");
        dialog.querySelector("[data-rich-link-text]").value = editor.state.doc.textBetween(this.linkRange.from, this.linkRange.to, " ");
        dialog.querySelector("[data-rich-link-url]").value = editor.getAttributes("link").href || "";
        dialog.querySelector("[data-rich-link-error]").hidden = true;
        dialog.showModal();
        dialog.querySelector("[data-rich-link-url]").focus();
    }

    applyLink(remove = false) {
        const dialog = this.form.querySelector("[data-rich-link-dialog]");
        const editor = this.linkEditor;
        if (!editor || editor.isDestroyed) return;
        if (remove) {
            editor.chain().focus().setTextSelection(this.linkRange).unsetLink().run();
            dialog.close();
            return;
        }
        let href = dialog.querySelector("[data-rich-link-url]").value.trim();
        if (!/^[a-z][a-z\d+.-]*:/i.test(href) && !href.startsWith("/") && !href.startsWith("#")) href = "https://" + href;
        try {
            const url = new URL(href, location.origin);
            if (!["http:", "https:"].includes(url.protocol) || href.startsWith("//") || href.includes("\\")) throw new Error();
        } catch {
            const error = dialog.querySelector("[data-rich-link-error]");
            error.textContent = "Enter a valid http or https link.";
            error.hidden = false;
            return;
        }
        const text = dialog.querySelector("[data-rich-link-text]").value || href;
        editor.chain().focus().insertContentAt(this.linkRange, {type: "text", text, marks: [{type: "link", attrs: {href, target: href.startsWith("/") ? null : "_blank", rel: "noopener noreferrer"}}]})
            .command(({tr}) => { tr.removeStoredMark(editor.schema.marks.link); return true; }).run();
        dialog.close();
    }

    insertImages(editor, files) {
        const accepted = files.filter(file => ["image/jpeg", "image/png", "image/webp", "image/gif"].includes(file.type) && file.size <= 10 * 1024 * 1024);
        if (accepted.length !== files.length) notify({kind: "warning", title: "Choose an image", message: "Use JPEG, PNG, WebP or GIF images up to 10 MB each."});
        if (!accepted.length) return;
        const previousUploads = [...this.form.journalPendingUploads];
        const operation = (async () => {
            await Promise.all(previousUploads);
            if (!await saveJournalEditor(this.form, {skipUploads: true})) return;
            const section = editor.view.dom.closest("[data-journal-section]");
            for (const file of accepted) {
                if (editor.isDestroyed) return;
                const uploadId = crypto.randomUUID();
                const preview = URL.createObjectURL(file);
                editor.chain().focus().insertContentAt(editor.state.selection.to, {type: "image", attrs: {src: preview, alt: "Adding image…", uploadId}}).run();
                try {
                    const data = new FormData();
                    data.set("file", file);
                    data.set("section", section?.querySelector('[name$="-id"]')?.value || "");
                    const response = await fetch(this.form.dataset.uploadUrl, {method: "POST", body: data,
                        headers: {"Accept": "application/json", "X-CSRFToken": this.form.querySelector('[name="csrfmiddlewaretoken"]').value}, signal: AbortSignal.timeout(60000)});
                    const result = await response.json();
                    if (!response.ok) throw new Error(result.message || "The image could not be added.");
                    if (!editor.isDestroyed) {
                        editor.state.doc.descendants((node, position) => {
                            if (node.type.name === "image" && node.attrs.uploadId === uploadId) {
                                editor.view.dispatch(editor.state.tr.setNodeMarkup(position, undefined, {...node.attrs, src: result.src, attachmentId: result.id, alt: file.name, width: Math.min(result.width, 640), height: null, uploadId: null}).setMeta("addToHistory", false));
                                return false;
                            }
                        });
                    }
                } catch (error) {
                    if (!editor.isDestroyed) {
                        let position;
                        editor.state.doc.descendants((node, pos) => { if (node.attrs.uploadId === uploadId) position = pos; });
                        if (position !== undefined) editor.view.dispatch(editor.state.tr.delete(position, position + 1).setMeta("addToHistory", false));
                    }
                    notify({kind: "error", title: "Image not added", message: error.message || "Try adding the image again."});
                } finally { URL.revokeObjectURL(preview); }
            }
        })();
        this.form.journalPendingUploads.add(operation);
        void operation.catch(error => notify({kind: "error", title: "Image not added", message: error.message})).finally(() => this.form.journalPendingUploads.delete(operation));
    }

    async export(format) {
        this.closeMenus();
        const printWindow = format === "pdf" ? window.open("about:blank", "_blank") : null;
        try {
            if (!await saveJournalEditor(this.form)) { printWindow?.close(); return; }
            const url = this.form.dataset.exportUrl.replace(/docx\/$/, `${format}/`);
            if (format === "pdf") {
                if (printWindow) { printWindow.opener = null; printWindow.location.replace(url); }
                else notify({kind: "warning", title: "Allow the print window", message: "Allow popups for this app, then try PDF / Print again."});
                return;
            }
            const response = await fetch(url);
            if (!response.ok) throw new Error(await response.text());
            const blob = URL.createObjectURL(await response.blob());
            const link = document.createElement("a");
            link.href = blob;
            link.download = response.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] || "journal.docx";
            link.click();
            setTimeout(() => URL.revokeObjectURL(blob), 10000);
        } catch (error) {
            printWindow?.close();
            notify({kind: "error", title: "Export unavailable", message: error.message || "Try exporting again."});
        }
    }

    destroy() {
        for (const editor of this.editors.values()) editor.destroy();
        this.editors.clear();
        controllers.delete(this.form);
    }
}

export function refreshRichEditors(form) { controllers.get(form)?.refresh(); }
export function focusRichEditor(field) {
    const form = field?.closest("[data-journal-editor]");
    controllers.get(form)?.editors.get(field)?.commands.focus();
}

export function registerJournalRichtext() {
    if (registered) return;
    registered = true;
    document.addEventListener("world-journal:page-ready", () => {
        const form = document.querySelector("[data-journal-editor]");
        if (!form) return;
        for (const [previous, controller] of controllers) if (previous !== form && !previous.isConnected) {
            void Promise.all(previous.journalPendingUploads || []).then(() => controller.destroy());
        }
        if (controllers.has(form)) { controllers.get(form).refresh(); return; }
        if (form.journalReady) return;
        library ||= import("../../vendor/tiptap/editor.js");
        form.journalReady = library.then(modules => {
            const controller = new JournalEditor(form, modules);
            controllers.set(form, controller);
            controller.syncToolbar();
        });
        void form.journalReady.catch(() => notify({kind: "error", title: "Editor unavailable", message: "Reload this page to open the editor. Your saved writing is unchanged."}));
    });
    document.addEventListener("world-journal:page-cleanup", event => {
        if (event.detail?.page !== "journal" || event.detail.preserveJournal) return;
        const form = document.querySelector("[data-journal-editor]");
        if (form) void Promise.all([form.journalReady, ...(form.journalPendingUploads || [])]).then(() => controllers.get(form)?.destroy()).catch(() => {});
    });
    document.addEventListener("pointerdown", event => {
        if (event.target.closest("[data-rich-command], [data-rich-link], [data-rich-image], [data-rich-menu] > summary")) event.preventDefault();
    });
    document.addEventListener("click", event => {
        for (const controller of controllers.values()) for (const menu of controller.form.querySelectorAll("[data-rich-menu][open]")) {
            if (!menu.contains(event.target)) menu.open = false;
        }
        const form = event.target.closest("[data-journal-editor]");
        const controller = controllers.get(form);
        if (!controller) return;
        const command = event.target.closest("[data-rich-command]");
        if (command) controller.command(command.dataset.richCommand);
        else if (event.target.closest("[data-rich-link]")) controller.openLink();
        else if (event.target.closest("[data-rich-image]")) form.querySelector("[data-rich-image-input]").click();
        else if (event.target.closest("[data-rich-link-apply]")) controller.applyLink();
        else if (event.target.closest("[data-rich-link-remove]")) controller.applyLink(true);
        else if (event.target.closest("[data-rich-link-cancel]")) form.querySelector("[data-rich-link-dialog]").close();
        else if (event.target.closest("[data-journal-export]")) void controller.export(event.target.closest("[data-journal-export]").dataset.journalExport);
    });
    document.addEventListener("change", event => {
        const controller = controllers.get(event.target.closest("[data-journal-editor]"));
        const editor = controller?.active();
        if (!editor) return;
        const field = event.target;
        const chain = editor.chain().focus();
        if (field.matches("[data-rich-style]")) field.value === "paragraph" ? chain.setParagraph().run() : chain.setHeading({level: Number(field.value)}).run();
        else if (field.matches("[data-rich-font]")) field.value ? chain.setFontFamily(field.value).run() : chain.unsetFontFamily().run();
        else if (field.matches("[data-rich-size]")) field.value ? chain.setFontSize(field.value).run() : chain.unsetFontSize().run();
        else if (field.matches("[data-rich-color]")) chain.setColor(field.value).run();
        else if (field.matches("[data-rich-highlight]")) chain.setBackgroundColor(field.value).run();
        else if (field.matches("[data-rich-image-input]")) { controller.insertImages(editor, [...field.files]); field.value = ""; }
    });
    document.addEventListener("keydown", event => {
        const controller = controllers.get(event.target.closest("[data-journal-editor]"));
        if (!controller) return;
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); controller.openLink(); }
        if (event.key === "Enter" && event.target.closest("[data-rich-link-dialog]")) { event.preventDefault(); controller.applyLink(); }
        if (event.key === "Escape") controller.closeMenus();
    });
}
