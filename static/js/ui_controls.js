// Progressive enhancement: native fields remain the source of truth for forms.
const controls = new WeakMap();
let activeControl = null;
let registered = false;
let nextId = 0;

function normalize(value) {
    return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
}

function icon(name) {
    return document.querySelector(`[data-control-icon="${name}"]`)?.content.cloneNode(true)
        || document.createDocumentFragment();
}

class SelectControl {
    constructor(select) {
        this.select = select;
        // HTMX history snapshots can restore generated markup without its JS
        // controller. Rebuild around the native field instead of nesting menus.
        const restoredWrapper = select.closest(".select-control");
        if (restoredWrapper) {
            restoredWrapper.before(select);
            restoredWrapper.remove();
        }
        const hadFocus = document.activeElement === select;
        this.country = select.hasAttribute("data-country-select")
            || [...select.options].filter(option => /^[A-Z]{2}$/.test(option.value)).length > 5;
        this.wrapper = document.createElement("div");
        this.wrapper.className = "select-control";
        select.before(this.wrapper);
        this.wrapper.append(select);
        select.classList.add("select-native");
        select.style.setProperty("display", "none", "important");
        select.tabIndex = -1;
        select.setAttribute("aria-hidden", "true");
        const id = `custom-select-${++nextId}`;
        const labels = [...select.labels];
        this.label = labels.map(label => label.textContent.trim()).join(" ") || "Choose an option";
        this.trigger = document.createElement("button");
        this.trigger.type = "button";
        this.trigger.className = "select-trigger";
        this.trigger.setAttribute("role", "combobox");
        this.trigger.setAttribute("aria-haspopup", "listbox");
        this.trigger.setAttribute("aria-expanded", "false");
        this.trigger.setAttribute("aria-controls", `${id}-list`);
        this.value = document.createElement("span");
        this.value.className = "select-value";
        this.value.id = `${id}-value`;
        if (labels.length) {
            labels.forEach((label, index) => { if (!label.id) label.id = `${id}-label-${index}`; });
            this.trigger.setAttribute("aria-labelledby", `${labels.map(label => label.id).join(" ")} ${this.value.id}`);
        } else {
            this.trigger.setAttribute("aria-label", this.label);
        }
        this.trigger.append(this.value, icon("down"));
        this.tags = document.createElement("div");
        this.tags.className = "select-tags";
        this.error = document.createElement("p");
        this.error.className = "select-error";
        this.error.id = `${id}-error`;
        this.error.setAttribute("role", "alert");
        this.trigger.setAttribute("aria-describedby", [select.getAttribute("aria-describedby"), this.error.id].filter(Boolean).join(" "));
        this.wrapper.append(this.trigger, this.tags, this.error);
        this.menu = document.createElement("div");
        this.menu.className = "select-menu";
        this.menu.hidden = true;
        this.search = document.createElement("input");
        this.search.type = "search";
        this.search.className = "select-search";
        this.search.placeholder = this.country ? "Search countries…" : "Search options…";
        this.search.setAttribute("aria-label", this.country ? "Search countries" : `Search ${this.label}`);
        this.search.autocomplete = "off";
        this.search.spellcheck = false;
        this.list = document.createElement("div");
        this.list.className = "select-options";
        this.list.id = `${id}-list`;
        this.list.setAttribute("role", "listbox");
        this.list.setAttribute("aria-label", this.label);
        this.list.setAttribute("aria-multiselectable", String(select.multiple));
        this.status = document.createElement("p");
        this.status.className = "select-status";
        this.status.setAttribute("aria-live", "polite");
        this.menu.append(this.search, this.list, this.status);
        if (select.multiple) {
            const done = document.createElement("button");
            done.type = "button";
            done.className = "select-done";
            done.textContent = "Done";
            done.addEventListener("click", () => this.close(true));
            this.menu.append(done);
        }
        this.trigger.addEventListener("click", () => this.menu.hidden ? this.open() : this.close(true));
        this.trigger.addEventListener("keydown", event => {
            if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
                event.preventDefault();
                this.open(false);
                this.focusOption(event.key === "End" || event.key === "ArrowUp" ? -1 : 0);
            } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && event.key !== " ") {
                event.preventDefault();
                this.open();
                this.search.value = event.key;
                this.renderOptions();
            }
        });
        this.search.addEventListener("input", () => this.renderOptions());
        this.menu.addEventListener("keydown", event => this.onMenuKey(event));
        select.addEventListener("change", () => this.sync());
        select.addEventListener("focus", () => this.trigger.focus());
        select.addEventListener("invalid", event => {
            event.preventDefault();
            for (let parent = select.parentElement; parent; parent = parent.parentElement) {
                if (parent.matches("details")) parent.open = true;
            }
            this.error.textContent = select.validationMessage;
            this.trigger.setAttribute("aria-invalid", "true");
            this.open();
        });
        this.sync();
        if (hadFocus) this.trigger.focus({preventScroll: true});
    }

    sync() {
        this.trigger.disabled = this.select.matches(":disabled");
        this.trigger.setAttribute("aria-required", String(this.select.required));
        const selected = [...this.select.selectedOptions].filter(option => !this.select.multiple || option.value);
        const text = selected.length ? selected.map(option => option.textContent.trim()).join(", ")
            : this.country ? "Choose countries" : "Choose an option";
        if (this.value.textContent !== text) this.value.textContent = text;
        this.trigger.title = text;
        this.tags.replaceChildren();
        if (this.select.multiple) {
            for (const option of selected) {
                const tag = document.createElement("button");
                tag.type = "button";
                tag.className = "select-tag";
                tag.append(document.createTextNode(option.textContent.trim()), icon("close"));
                tag.setAttribute("aria-label", `Remove ${option.textContent.trim()}`);
                tag.disabled = this.select.matches(":disabled") || option.disabled;
                tag.addEventListener("click", () => {
                    option.selected = false;
                    this.select.dispatchEvent(new Event("change", {bubbles: true}));
                    this.trigger.focus();
                });
                this.tags.append(tag);
            }
        }
        this.tags.hidden = !this.select.multiple || !selected.length;
        if (this.select.validity.valid) {
            this.error.textContent = "";
            this.trigger.removeAttribute("aria-invalid");
        }
        if (this.select.matches(":disabled") || !this.select.isConnected) this.close();
        else if (!this.menu.hidden) this.renderOptions();
    }

    renderOptions() {
        const tokens = normalize(this.search.value.trim()).split(/\s+/).filter(Boolean);
        const focusedIndex = this.list.contains(document.activeElement) ? document.activeElement.dataset.optionIndex : null;
        this.list.replaceChildren();
        let count = 0;
        for (const [index, option] of [...this.select.options].entries()) {
            if (option.hidden || !tokens.every(token => normalize(`${option.textContent} ${option.value}`).includes(token))) continue;
            const button = document.createElement("button");
            button.type = "button";
            button.className = "select-option";
            button.dataset.optionIndex = index;
            button.setAttribute("role", "option");
            button.setAttribute("aria-selected", String(option.selected));
            button.tabIndex = -1;
            button.disabled = option.disabled || option.parentElement.disabled === true;
            button.textContent = option.textContent.trim();
            button.addEventListener("click", () => {
                if (this.select.multiple) option.selected = !option.selected;
                else this.select.selectedIndex = index;
                this.select.dispatchEvent(new Event("change", {bubbles: true}));
                if (this.select.multiple && !this.menu.hidden) this.list.querySelector(`[data-option-index="${index}"]`)?.focus();
                else this.close(true);
            });
            this.list.append(button);
            count++;
        }
        const selectedCount = [...this.select.selectedOptions].filter(option => option.value).length;
        this.status.textContent = !count ? "No matching options" : this.select.multiple ? `${selectedCount} selected` : "";
        if (focusedIndex !== null) this.list.querySelector(`[data-option-index="${focusedIndex}"]`)?.focus();
        if (!this.menu.hidden) this.position();
    }

    open(focusSearch = true) {
        if (this.select.matches(":disabled") || !this.select.isConnected) return;
        activeControl?.close();
        activeControl = this;
        this.search.value = "";
        this.search.hidden = !(this.country || this.select.options.length > 7);
        this.menu.hidden = false;
        document.body.append(this.menu);
        this.trigger.setAttribute("aria-expanded", "true");
        this.renderOptions();
        if (focusSearch && !this.search.hidden) this.search.focus({preventScroll: true});
        else this.focusOption(0);
    }

    close(restoreFocus = false) {
        this.menu.hidden = true;
        this.menu.remove();
        this.trigger.setAttribute("aria-expanded", "false");
        if (activeControl === this) activeControl = null;
        if (restoreFocus && this.trigger.isConnected && !this.trigger.disabled) this.trigger.focus({preventScroll: true});
    }

    position() {
        const rect = this.trigger.getBoundingClientRect();
        const viewport = window.visualViewport;
        const viewportTop = viewport?.offsetTop || 0;
        const viewportHeight = viewport?.height || window.innerHeight;
        const viewportBottom = viewportTop + viewportHeight;
        const below = viewportBottom - rect.bottom - 12;
        const above = rect.top - viewportTop - 12;
        const upwards = below < 240 && above > below;
        const viewportWidth = document.documentElement.clientWidth;
        const width = Math.min(Math.max(rect.width, 260), viewportWidth - 24);
        this.menu.style.width = `${width}px`;
        this.menu.style.maxHeight = `${Math.max(80, Math.min(400, upwards ? above : below))}px`;
        this.menu.style.left = `${Math.max(12, Math.min(rect.left, viewportWidth - width - 12))}px`;
        this.menu.style.top = `${Math.max(viewportTop + 12, upwards ? rect.top - this.menu.offsetHeight - 8 : rect.bottom + 8)}px`;
    }

    focusOption(index) {
        const options = [...this.list.querySelectorAll(".select-option:not(:disabled)")];
        const option = index < 0 ? options.at(-1) : options[index];
        option?.focus({preventScroll: true});
        option?.scrollIntoView({block: "nearest"});
    }

    onMenuKey(event) {
        if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); this.close(true); return; }
        if (event.key === "Tab") {
            this.close(true);
            const focusable = [...document.querySelectorAll('a[href], button, input, select, textarea, [tabindex]')]
                .filter(element => element.tabIndex >= 0 && !element.disabled && element.getClientRects().length);
            const next = focusable[focusable.indexOf(this.trigger) + (event.shiftKey ? -1 : 1)];
            if (next) { event.preventDefault(); next.focus(); }
            return;
        }
        if (event.target === this.search && ["Home", "End"].includes(event.key)) return;
        const options = [...this.list.querySelectorAll(".select-option:not(:disabled)")];
        const index = options.indexOf(document.activeElement);
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
            event.preventDefault();
            this.focusOption(event.key === "Home" ? 0 : event.key === "End" ? -1
                : index < 0 ? (event.key === "ArrowUp" ? -1 : 0)
                : (index + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length);
        } else if (event.key.length === 1 && event.target !== this.search && !this.search.hidden && !event.ctrlKey && !event.metaKey && event.key !== " ") {
            event.preventDefault(); this.search.focus(); this.search.value += event.key; this.renderOptions();
        }
    }
}

function enhance(root) {
    for (const select of root.querySelectorAll("select")) {
        if (select.hidden || select.id === "theme-selector" || select.hasAttribute("data-native-select")) continue;
        if (!controls.has(select)) controls.set(select, new SelectControl(select));
        else controls.get(select).sync();
    }
    for (const input of root.querySelectorAll('input[type="checkbox"]')) {
        const label = input.closest("label") || input.labels[0];
        if (!label) continue;
        if (!label.contains(input)) label.prepend(input);
        label.classList.add("toggle-choice");
    }
}

export function registerUiControls() {
    if (registered) return;
    registered = true;
    const content = document.querySelector("#app-content");
    const observer = new MutationObserver(records => {
        const added = new Set();
        const changed = new Set();
        for (const record of records) {
            const target = record.target.nodeType === Node.ELEMENT_NODE ? record.target : record.target.parentElement;
            const select = target?.closest("select");
            if (select && controls.has(select)) changed.add(select);
            for (const node of record.addedNodes) {
                if (node.nodeType === Node.ELEMENT_NODE && (node.matches('select, input[type="checkbox"]') || node.querySelector('select, input[type="checkbox"]'))) added.add(node.parentElement || node);
            }
        }
        for (const root of added) if (root.isConnected) enhance(root);
        for (const select of changed) if (select.isConnected) controls.get(select).sync();
        if (activeControl && !activeControl.wrapper.isConnected) activeControl.close();
    });
    observer.observe(content, {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["disabled", "selected", "label"]});
    document.addEventListener("world-journal:page-ready", () => enhance(content));
    document.addEventListener("world-journal:page-cleanup", () => activeControl?.close());
    document.addEventListener("pointerdown", event => {
        if (activeControl && !activeControl.wrapper.contains(event.target) && !activeControl.menu.contains(event.target)) activeControl.close();
    });
    window.addEventListener("scroll", event => {
        if (!activeControl || (event.target instanceof Node && activeControl.menu.contains(event.target))) return;
        const rect = activeControl.trigger.getBoundingClientRect();
        if (!rect.width || rect.bottom < 0 || rect.top > window.innerHeight) activeControl.close();
        else activeControl.position();
    }, true);
    window.addEventListener("resize", () => activeControl?.position());
    window.visualViewport?.addEventListener("resize", () => activeControl?.position());
    document.addEventListener("reset", () => queueMicrotask(() => enhance(content)));
    enhance(content);
}
