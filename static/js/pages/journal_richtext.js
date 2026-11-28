import { notify } from "../notifications.js";
import { refreshSelectControl } from "../ui_controls.js";
import { saveJournalEditor } from "./journal_autosave.js";
import { randomId } from "../random_id.js";
import { journalVideoThumbnails, refreshJournalVideos } from "./journal_video.js";

const controllers = new Map();
let library;
let registered = false;
const normalize = value => value.normalize("NFC").trim().replace(/\s+/g, " ").toLocaleLowerCase();
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const alignments = ["left", "center", "right", "justify"];
const imageSelected = editor => editor.state.selection.node?.type.name === "image";

function colorValue(value) {
    if (typeof value !== "string" || !value) return null;
    if (/^#[a-f\d]{6}$/i.test(value)) return value.toLowerCase();
    if (/^#[a-f\d]{3}$/i.test(value)) return "#" + [...value.slice(1)].map(char => char + char).join("").toLowerCase();
    const match = value.match(/^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/);
    return match ? "#" + match.slice(1).map(number => Number(number).toString(16).padStart(2, "0")).join("") : null;
}

function highlightInk(value) {
    const color = colorValue(value);
    if (!color) return null;
    const [red, green, blue] = [1, 3, 5].map(start => parseInt(color.slice(start, start + 2), 16));
    return red * .299 + green * .587 + blue * .114 >= 140 ? "dark" : "light";
}

function selectionFormatting(editor) {
    const {selection, storedMarks, doc} = editor.state;
    const samples = [], blocks = [];
    const addMarks = marks => samples.push(marks.find(mark => mark.type.name === "textStyle")?.attrs || {});
    if (selection.empty) {
        // An empty stored-mark set deliberately clears formatting at the caret.
        addMarks(storedMarks ?? selection.$from.marks());
        if (["paragraph", "heading"].includes(selection.$from.parent.type.name)) blocks.push(selection.$from.parent);
    } else doc.nodesBetween(selection.from, selection.to, node => {
        if (node.isText) addMarks(node.marks);
        if (["paragraph", "heading"].includes(node.type.name)) blocks.push(node);
    });
    const values = {}, mixed = new Set();
    for (const property of ["color", "backgroundColor", "fontFamily", "fontSize"]) {
        const options = new Set(samples.map(style => property.endsWith("Color") || property === "color" ? colorValue(style[property]) : style[property] || null));
        values[property] = options.size === 1 ? [...options][0] : null;
        if (options.size > 1) mixed.add(property);
    }
    const positions = new Set(blocks.map(node => node.attrs.textAlign || "left"));
    const styles = new Set(blocks.map(node => node.type.name === "heading" ? String(node.attrs.level) : "paragraph"));
    return {values, mixed, alignment: positions.size === 1 ? [...positions][0] : null, style: styles.size === 1 ? [...styles][0] : "paragraph", mixedStyle: styles.size > 1, alignable: blocks.length > 0};
}

function syncSelect(select, value, mixed = false) {
    const wanted = mixed ? "__mixed" : value || "";
    let extra = select.querySelector("[data-editor-custom]");
    if (extra && extra.value !== wanted) { extra.remove(); extra = null; }
    if (wanted && ![...select.options].some(option => option.value === wanted)) {
        extra = new Option(mixed ? "Mixed" : wanted.replace(/px$/, ""), wanted);
        extra.dataset.editorCustom = "true";
        extra.disabled = true;
        select.append(extra);
    }
    if (select.value !== wanted) {
        select.value = wanted;
        refreshSelectControl(select);
    }
}

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
                }, uploadId: {default: null, rendered: false}, alignment: {
                    default: "left",
                    parseHTML: element => element.getAttribute("data-image-align") || "left",
                    renderHTML: attrs => ({"data-image-align": attrs.alignment}),
                }};
            },
            parseHTML() {
                return [{tag: "img[data-attachment-id]", getAttrs: element => uuid.test(element.getAttribute("data-attachment-id")) ? null : false}];
            },
            addInputRules() { return []; },
            addNodeView() {
                const createView = this.parent?.();
                if (!createView) return null;
                return props => {
                    const view = createView(props);
                    const sync = node => {
                        view.dom.dataset.imageAlign = node.attrs.alignment || "left";
                        const image = view.dom.querySelector("img");
                        image.style.width = node.attrs.width ? `${node.attrs.width}px` : "";
                        image.style.height = "auto";
                    };
                    const update = view.update.bind(view);
                    view.update = (node, ...rest) => {
                        const result = update(node, ...rest);
                        if (result) sync(node);
                        return result;
                    };
                    sync(props.node);
                    return view;
                };
            },
        });
        const ContentAlign = TextAlign.extend({
            addCommands() {
                const parent = this.parent();
                return {...parent,
                    setTextAlign: alignment => props => {
                        if (props.state.selection.node?.type.name === "image") return ["left", "center", "right"].includes(alignment) && props.commands.updateAttributes("image", {alignment});
                        return parent.setTextAlign(alignment)(props);
                    },
                    unsetTextAlign: () => props => props.state.selection.node?.type.name === "image"
                        ? props.commands.resetAttributes("image", "alignment") : parent.unsetTextAlign()(props),
                };
            },
        });
        const HighlightContrast = Extension.create({
            name: "highlightContrast",
            addGlobalAttributes() {
                return [{types: ["textStyle"], attributes: {autoInk: {
                    default: null,
                    parseHTML: () => null,
                    renderHTML: attrs => {
                        const ink = !attrs.color && highlightInk(attrs.backgroundColor);
                        return ink ? {"data-highlight-ink": ink} : {};
                    },
                }}}];
            },
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
                TaskList, TaskItem.configure({nested: true, HTMLAttributes: {"data-type": "taskItem"}}), ContentAlign.configure({types: ["heading", "paragraph"]}),
                TextStyleKit, HighlightContrast, Placeholder.configure({placeholder: "Start writing…"}), CountryLinks,
                journalVideoThumbnails(this.modules),
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
                refreshJournalVideos(field.closest("[data-editor-page]"));
            },
            onSelectionUpdate: () => this.syncToolbar(),
            onTransaction: () => this.syncToolbar(),
        });
        this.editors.set(field, editor);
        this.syncField(field, editor);
        delete root.dataset.legacyHtml;
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
        refreshJournalVideos(this.form);
    }

    syncToolbar() {
        const editor = this.active();
        if (!editor || editor.isDestroyed) return;
        const isImage = imageSelected(editor);
        const formatting = selectionFormatting(editor);
        const alignment = isImage ? editor.getAttributes("image").alignment || "left" : formatting.alignment;
        for (const button of this.toolbar.querySelectorAll("[data-rich-command]")) {
            const command = button.dataset.richCommand;
            if (button.hasAttribute("aria-pressed")) button.setAttribute("aria-pressed", String(alignments.includes(command) ? alignment === command : editor.isActive(command)));
            if (!editor.isEditable) button.disabled = true;
            else if (["undo", "redo"].includes(command)) button.disabled = !editor.can()[command]();
            else if (button.hasAttribute("data-table-action")) button.disabled = !editor.isActive("table") || !editor.can()[command]();
            else if (alignments.includes(command)) button.disabled = isImage ? command === "justify" : !formatting.alignable;
            else if (button.hasAttribute("data-text-action")) button.disabled = isImage || !editor.can()[`toggle${command[0].toUpperCase()}${command.slice(1)}`]();
            else button.disabled = false;
        }
        const style = this.toolbar.querySelector("[data-rich-style]");
        syncSelect(style, formatting.style, formatting.mixedStyle);
        syncSelect(this.toolbar.querySelector("[data-rich-font]"), formatting.values.fontFamily, formatting.mixed.has("fontFamily"));
        syncSelect(this.toolbar.querySelector("[data-rich-size]"), formatting.values.fontSize, formatting.mixed.has("fontSize"));
        for (const control of this.toolbar.querySelectorAll("select, [data-text-action]:not([data-rich-command])")) {
            const disabled = !editor.isEditable || isImage || (control !== style && editor.isActive("codeBlock"));
            if (control.disabled !== disabled) control.disabled = disabled;
        }
        for (const option of style.options) {
            if (!/^[1-3]$/.test(option.value)) continue;
            const disabled = !editor.can().setHeading({level: Number(option.value)});
            if (option.disabled !== disabled) option.disabled = disabled;
        }
        for (const menu of this.toolbar.querySelectorAll("[data-text-menu]")) {
            menu.inert = !editor.isEditable || isImage || (menu.hasAttribute("data-color-menu") && editor.isActive("codeBlock"));
            if (menu.inert) menu.open = false;
        }
        const list = ["bulletList", "orderedList", "taskList"].find(type => editor.isActive(type));
        const listMenu = this.toolbar.querySelector(".journal-list-menu");
        listMenu.dataset.active = String(Boolean(list));
        for (const icon of listMenu.querySelectorAll("[data-list-icon]")) icon.hidden = icon.dataset.listIcon !== (list || "bulletList");
        for (const menu of this.toolbar.querySelectorAll("[data-color-menu]")) {
            const property = menu.dataset.colorMenu;
            const color = formatting.values[property];
            const mixed = formatting.mixed.has(property);
            menu.dataset.hasColor = String(Boolean(color));
            menu.dataset.mixed = String(mixed);
            menu.style.setProperty("--selected-color", color || (property === "color" ? "currentColor" : "transparent"));
            const label = (property === "color" ? "Text colour" : "Highlight colour") + (mixed ? " (mixed)" : "");
            menu.querySelector("summary").title = label;
            menu.querySelector("summary").setAttribute("aria-label", label);
            for (const swatch of menu.querySelectorAll("[data-rich-color-value]")) swatch.setAttribute("aria-pressed", String(!mixed && (swatch.dataset.richColorValue || null) === color));
            const picker = menu.querySelector("[data-rich-custom-color]");
            if (color && document.activeElement !== picker) picker.value = color;
        }
    }

    setColor(menu, value, close = true) {
        const editor = this.active();
        if (!editor?.isEditable || imageSelected(editor)) return;
        const background = menu.dataset.colorMenu === "backgroundColor";
        const chain = editor.chain().focus();
        if (background) value ? chain.setBackgroundColor(value).run() : chain.unsetBackgroundColor().run();
        else value ? chain.setColor(value).run() : chain.unsetColor().run();
        this.syncToolbar();
        if (close) this.closeMenus();
    }

    command(name) {
        const editor = this.active();
        if (!editor?.isEditable) return;
        const chain = editor.chain().focus();
        if (["bold", "italic", "underline", "strike", "bulletList", "orderedList", "taskList", "blockquote", "codeBlock"].includes(name)) {
            chain[`toggle${name[0].toUpperCase()}${name.slice(1)}`]().run();
        } else if (alignments.includes(name)) chain.setTextAlign(name).run();
        else if (name === "insertTable") {
            if (imageSelected(editor)) chain.createParagraphNear();
            chain.insertTable({rows: 3, cols: 3, withHeaderRow: true}).run();
        }
        else if (name === "horizontalRule") chain.insertContentAt(editor.state.selection.to, {type: "horizontalRule"}).run();
        else if (name === "clear") {
            if (imageSelected(editor)) chain.updateAttributes("image", {alignment: "left"}).run();
            else chain.unsetAllMarks().clearNodes().unsetTextAlign().run();
        }
        else if (typeof chain[name] === "function") chain[name]().run();
        this.closeMenus();
    }

    closeMenus() {
        for (const menu of this.form.querySelectorAll("[data-rich-menu][open]")) menu.open = false;
    }

    positionMenu(menu) {
        const panel = menu.querySelector(".journal-editor-menu-panel");
        if (!panel) return;
        const anchor = menu.getBoundingClientRect();
        const width = panel.getBoundingClientRect().width;
        const initial = menu.matches(".journal-list-menu, .journal-color-menu") ? 0 : anchor.width - width;
        panel.style.left = `${Math.max(8 - anchor.left, Math.min(initial, document.documentElement.clientWidth - 8 - anchor.left - width))}px`;
        panel.style.right = "auto";
    }

    openLink() {
        const editor = this.active();
        if (!editor?.isEditable || imageSelected(editor)) return;
        if (editor.isActive("link")) editor.commands.extendMarkRange("link");
        this.closeMenus();
        this.linkEditor = editor;
        this.linkRange = {from: editor.state.selection.from, to: editor.state.selection.to};
        const dialog = this.form.querySelector("[data-rich-link-dialog]");
        const href = editor.getAttributes("link").href || "";
        dialog.querySelector("#journal-link-title").textContent = href ? "Edit link" : "Insert link";
        dialog.querySelector("[data-rich-link-apply]").textContent = href ? "Save" : "Insert";
        dialog.querySelector("[data-rich-link-remove]").hidden = !href;
        dialog.querySelector("[data-rich-link-text]").value = editor.state.doc.textBetween(this.linkRange.from, this.linkRange.to, " ");
        dialog.querySelector("[data-rich-link-url]").value = href;
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
        const attrs = {href, target: href.startsWith("/") ? null : "_blank", rel: "noopener noreferrer"};
        const original = editor.state.doc.textBetween(this.linkRange.from, this.linkRange.to, " ");
        const chain = editor.chain().focus().setTextSelection(this.linkRange);
        if (original === text && this.linkRange.from !== this.linkRange.to) chain.setLink(attrs).setTextSelection(this.linkRange.to);
        else {
            const marks = (editor.state.doc.nodeAt(this.linkRange.from)?.marks || editor.state.storedMarks || editor.state.selection.$from.marks())
                .filter(mark => mark.type.name !== "link").map(mark => mark.toJSON());
            chain.insertContentAt(this.linkRange, {type: "text", text, marks: [...marks, {type: "link", attrs}]});
        }
        chain.command(({tr}) => { tr.removeStoredMark(editor.schema.marks.link); return true; }).run();
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
                const uploadId = randomId();
                const preview = URL.createObjectURL(file);
                editor.chain().focus().insertContentAt(editor.state.selection.to, {type: "image", attrs: {src: preview, alt: "Adding image…", uploadId}}).run();
                try {
                    const data = new FormData();
                    data.set("file", file);
                    data.set("section", section?.querySelector('[name$="-id"]')?.value || "");
                    data.set("inline", "1");
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
        delete this.form.journalReady;
        this.toolbar.inert = true;
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
            void Promise.all(previous.journalPendingUploads || []).then(() => { if (!previous.isConnected) controller.destroy(); });
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
        if (event.target.closest("[data-rich-command], [data-rich-color-value], [data-rich-color-custom-apply], [data-rich-link], [data-rich-image], [data-rich-menu] > summary")) event.preventDefault();
    });
    document.addEventListener("pointerenter", event => {
        const menu = event.target;
        if (!(menu instanceof HTMLElement) || !menu.matches("[data-rich-hover-menu]") || menu.inert || event.pointerType === "touch") return;
        const controller = controllers.get(menu.closest("[data-journal-editor]"));
        controller?.closeMenus();
        menu.open = true;
    }, true);
    document.addEventListener("pointerleave", event => {
        const menu = event.target;
        if (menu instanceof HTMLElement && menu.matches("[data-rich-hover-menu]") && !menu.contains(document.activeElement)) menu.open = false;
    }, true);
    document.addEventListener("focusout", event => {
        const menu = event.target.closest("[data-rich-menu]");
        if (menu && event.relatedTarget && !menu.contains(event.relatedTarget) && !menu.matches(":hover")) menu.open = false;
    });
    document.addEventListener("toggle", event => {
        const menu = event.target;
        if (!menu.matches?.("[data-rich-menu]") || !menu.open) return;
        controllers.get(menu.closest("[data-journal-editor]"))?.positionMenu(menu);
    }, true);
    window.addEventListener("resize", () => {
        for (const controller of controllers.values()) for (const menu of controller.form.querySelectorAll("[data-rich-menu][open]")) controller.positionMenu(menu);
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
        else if (event.target.closest("[data-rich-color-value]")) {
            const swatch = event.target.closest("[data-rich-color-value]");
            controller.setColor(swatch.closest("[data-color-menu]"), swatch.dataset.richColorValue);
        }
        else if (event.target.closest("[data-rich-color-custom-apply]")) {
            const menu = event.target.closest("[data-color-menu]");
            controller.setColor(menu, menu.querySelector("[data-rich-custom-color]").value);
        }
        else if (event.target.closest("[data-rich-link]")) controller.openLink();
        else if (event.target.closest("[data-rich-image]")) form.querySelector("[data-rich-image-input]").click();
        else if (event.target.closest("[data-rich-link-apply]")) controller.applyLink();
        else if (event.target.closest("[data-rich-link-remove]")) controller.applyLink(true);
        else if (event.target.closest("[data-rich-link-close]")) form.querySelector("[data-rich-link-dialog]").close();
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
        else if (field.matches("[data-rich-custom-color]")) controller.setColor(field.closest("[data-color-menu]"), field.value, false);
        else if (field.matches("[data-rich-image-input]")) { controller.insertImages(editor, [...field.files]); field.value = ""; }
        controller.syncToolbar();
    });
    document.addEventListener("keydown", event => {
        const controller = controllers.get(event.target.closest("[data-journal-editor]"));
        if (!controller) return;
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s" && !event.target.closest("dialog")) {
            event.preventDefault();
            controller.form.requestSubmit(controller.form.querySelector("[data-journal-save]"));
        }
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k" && event.target.closest(".journal-rich-editor")) { event.preventDefault(); controller.openLink(); }
        if (event.key === "Enter" && event.target.matches("[data-rich-link-dialog] input")) { event.preventDefault(); controller.applyLink(); }
        if (event.key === "ArrowDown" && event.target.matches("[data-rich-menu] > summary")) {
            event.preventDefault();
            const menu = event.target.closest("[data-rich-menu]");
            menu.open = true;
            menu.querySelector("button:not(:disabled)")?.focus();
        }
        if (event.key === "Escape" && controller.form.querySelector("[data-rich-menu][open]")) {
            event.preventDefault();
            controller.closeMenus();
            controller.active()?.commands.focus();
        }
    });
}
