// Color groups are UI state; the database continues storing one color per country.
import { beginTask, confirmAction, notify } from "../notifications.js";
import { presetColorValue } from "../preset_colors.js";
const VALID_COLOR = /^#[0-9a-f]{6}$/i;

function endpoint(controller, id) {
    return id === "new" ? controller.page.dataset.presetDataNewUrl
        : controller.page.dataset.presetDataUrlTemplate.replace("00000000-0000-0000-0000-000000000000", id);
}

function preview(controller) {
    const state = controller.presetEditor;
    const draft = state.draft;
    state.preview = draft ? {
        colors: Object.fromEntries(draft.groups.flatMap(group => group.countries.map(code => [code, group.color]))),
        defaultColor: VALID_COLOR.test(draft.default_color) ? draft.default_color : "",
    } : {colors: {}, defaultColor: ""};
    state.apply();
}

function announceLocation() {
    document.dispatchEvent(new CustomEvent("world-journal:location-change"));
}

function markChanged(controller) {
    const state = controller.presetEditor;
    state.draft.dirty = true;
    state.status.textContent = "Unsaved changes";
    preview(controller);
}

function button(text, className, action) {
    const element = document.createElement("button");
    element.type = "button";
    element.className = className;
    element.textContent = text;
    element.addEventListener("click", action);
    return element;
}

function setBusy(state, busy) {
    state.fields.disabled = busy;
    state.save.disabled = busy;
    state.drawer.setAttribute("aria-busy", String(busy));
    state.discard.disabled = state.saving;
    state.close.disabled = state.saving;
}

function colorControl(controller, value, onColor, {optional = false, label = "Group color", name = ""} = {}) {
    const control = controller.presetEditor.colorTemplate.content.firstElementChild.cloneNode(true);
    const input = control.querySelector("[data-map-color-value]");
    const native = control.querySelector("[data-map-color-native]");
    const clear = control.querySelector("[data-map-color-clear]");
    input.value = value;
    input.name = name;
    input.required = !optional;
    input.setAttribute("aria-label", `${label} (hex or RGB)`);
    native.setAttribute("aria-label", `Choose ${label.toLowerCase()}`);
    control.querySelector("[role=group]").setAttribute("aria-label", label);
    clear.hidden = !optional;
    function sync(color) {
        native.value = color || "#4a90e2";
        for (const choice of control.querySelectorAll("[data-map-color-choice]")) choice.setAttribute("aria-pressed", String(choice.dataset.mapColorChoice === color));
        clear.setAttribute("aria-pressed", String(!color));
    }
    function change(commit = false) {
        const color = presetColorValue(input.value);
        const valid = color !== null && (optional || Boolean(color));
        input.setCustomValidity(valid ? "" : "Use a hex color or RGB values from 0 to 255.");
        input.setAttribute("aria-invalid", String(!valid));
        if (!valid) return;
        const result = onColor(color, commit) ?? color;
        if (commit) input.value = result;
        sync(result);
    }
    input.addEventListener("input", () => change());
    input.addEventListener("change", () => change(true));
    native.addEventListener("input", () => { input.value = native.value; change(); });
    native.addEventListener("change", () => change(true));
    for (const choice of control.querySelectorAll("[data-map-color-choice]")) choice.addEventListener("click", () => {
        input.value = choice.dataset.mapColorChoice;
        change(true);
    });
    clear.addEventListener("click", () => { input.value = ""; change(true); });
    sync(value);
    return control;
}

function renderGroups(controller) {
    const state = controller.presetEditor;
    const draft = state.draft;
    state.rendering = true;
    state.countriesField.remove();
    state.groups.replaceChildren();
    draft.groups.forEach((group, index) => {
        const card = document.createElement("section");
        card.className = "preset-map-group";
        card.classList.toggle("is-active", index === draft.activeGroup);
        card.style.setProperty("--group-color", group.color);
        const heading = document.createElement("div");
        heading.className = "preset-map-group-heading";
        const choose = button("", "preset-map-group-select", () => {
            draft.activeGroup = index;
            renderGroups(controller);
            state.groups.children[index]?.querySelector(".preset-map-group-select").focus({preventScroll: true});
        });
        choose.append(document.querySelector('[data-control-icon="check"]').content.cloneNode(true));
        choose.setAttribute("aria-pressed", String(index === draft.activeGroup));
        const title = document.createElement("input");
        title.type = "text";
        title.className = "preset-map-group-title";
        title.maxLength = 160;
        title.value = group.title || "";
        title.placeholder = "Group title";
        title.setAttribute("aria-label", `Group ${index + 1} title`);
        const updateLabel = () => {
            choose.setAttribute("aria-label", `Select ${group.title?.trim() || `color group ${index + 1}`} for the map`);
        };
        updateLabel();
        title.addEventListener("input", () => { group.title = title.value; updateLabel(); markChanged(controller); });
        heading.append(choose, title, button("Remove", "preset-map-group-remove", async () => {
            if (group.countries.length && !await confirmAction({title: `Remove ${group.title?.trim() || "this color group"}?`, message: `This clears the color assigned to ${group.countries.length} countr${group.countries.length === 1 ? "y" : "ies"}. Save the preset afterward to keep the change.`, accept: "Remove group"})) return;
            if (!state.active || state.saving || state.draft !== draft || controller.abortController.signal.aborted) return;
            const active = draft.groups[draft.activeGroup];
            draft.groups.splice(draft.groups.indexOf(group), 1);
            draft.activeGroup = active !== group ? draft.groups.indexOf(active) : Math.max(0, Math.min(index, draft.groups.length - 1));
            markChanged(controller);
            renderGroups(controller);
        }));
        card.append(heading);
        if (index === draft.activeGroup) {
            let committedColor = group.color;
            const body = document.createElement("div");
            body.className = "preset-map-group-body";
            body.append(colorControl(controller, group.color, (color, commit) => {
                group.color = color;
                card.style.setProperty("--group-color", color);
                if (commit) {
                    const same = draft.groups.find(other => other !== group && other.color === color);
                    if (same) {
                        const combinedTitle = [...new Set([same.title, group.title].map(value => (value || "").trim()).filter(Boolean))].join(" / ");
                        if (combinedTitle.length > 160) {
                            group.color = committedColor;
                            card.style.setProperty("--group-color", committedColor);
                            preview(controller);
                            notify({kind: "warning", title: "Group titles are too long to combine", message: "Shorten the titles or choose a different color."});
                            return committedColor;
                        }
                        same.title = combinedTitle;
                        same.countries = [...new Set([...same.countries, ...group.countries])];
                        draft.groups.splice(index, 1);
                        draft.activeGroup = draft.groups.indexOf(same);
                        markChanged(controller);
                        renderGroups(controller);
                        return color;
                    }
                    committedColor = color;
                }
                markChanged(controller);
                return color;
            }, {label: `Group ${index + 1} color`}));
            body.append(state.countriesField);
            card.append(body);
        } else {
            const count = document.createElement("p");
            count.className = "preset-map-group-count";
            count.textContent = `${group.countries.length} ${group.countries.length === 1 ? "country" : "countries"}`;
            card.append(count);
        }
        state.groups.append(card);
    });
    const current = draft.groups[draft.activeGroup];
    state.countriesField.hidden = !current;
    if (!current) state.groups.after(state.countriesField);
    state.chips.replaceChildren();
    for (const code of [...(current?.countries || [])].sort((a, b) => controller.countriesByCode.get(a).name.localeCompare(controller.countriesByCode.get(b).name))) {
        const name = controller.countriesByCode.get(code).name;
        const remove = button(name, "preset-map-country-chip", () => {
            current.countries = current.countries.filter(value => value !== code);
            markChanged(controller);
            renderGroups(controller);
        });
        remove.setAttribute("aria-label", `Remove ${name} from this group`);
        remove.append(document.querySelector('[data-control-icon="close"]').content.cloneNode(true));
        state.chips.append(remove);
    }
    state.chips.hidden = !current?.countries.length;
    state.count.textContent = `${current?.countries.length || 0} ${current?.countries.length === 1 ? "country" : "countries"}`;
    const otherCodes = new Set(draft.groups.filter(group => group !== current).flatMap(group => group.countries));
    if (!state.countries.options.length) {
        for (const country of [...controller.countriesByCode.values()].sort((a, b) => a.name.localeCompare(b.name))) {
            state.countries.add(new Option(country.name, country.iso_a2));
        }
    }
    for (const option of state.countries.options) {
        option.selected = Boolean(current?.countries.includes(option.value));
        option.disabled = otherCodes.has(option.value);
    }
    state.countries.disabled = !current;
    state.add.disabled = draft.groups.length >= 238;
    // Keep the shared country selector synchronized without editing the draft.
    state.countries.dispatchEvent(new Event("change", {bubbles: true}));
    state.rendering = false;
}

function showDraft(controller) {
    const state = controller.presetEditor;
    const draft = state.draft;
    state.form.elements.name.value = draft.name;
    state.form.elements.description.value = draft.description;
    state.defaultColor.replaceChildren(colorControl(controller, draft.default_color, color => {
        draft.default_color = color;
        markChanged(controller);
    }, {optional: true, label: "Ungrouped countries color", name: "default_color"}));
    setBusy(state, state.saving);
    state.retry.hidden = true;
    state.status.textContent = draft.dirty ? "Unsaved changes" : "";
    renderGroups(controller);
    state.fields.scrollTop = 0;
    preview(controller);
}

export async function syncPresetEditor(controller, {reload = false} = {}) {
    const state = controller.presetEditor;
    if (!state) return;
    const id = new URL(location.href).searchParams.get("edit_preset");
    if (!id) {
        state.loadAbort?.abort();
        state.active = false;
        state.drawer.hidden = true;
        controller.page.classList.remove("has-preset-editor");
        if (!controller.selectedCode) controller.page.classList.remove("has-country-drawer");
        state.apply();
        controller.page.querySelector("[data-active-preset]").disabled = !controller.personal.ready || controller.personal.activating;
        return;
    }
    if (state.active && state.id === id && !reload) return;
    state.loadAbort?.abort();
    state.active = true;
    state.id = id;
    state.drawer.hidden = false;
    state.drawer.focus({preventScroll: true});
    controller.page.classList.add("has-country-drawer", "has-preset-editor");
    controller.page.querySelector("[data-active-preset]").disabled = true;
    state.draft = state.drafts.get(id);
    setBusy(state, true);
    state.status.textContent = "";
    state.retry.hidden = true;
    const abort = state.loadAbort = new AbortController();
    try {
        // Opening the drawer and clearing selection are independent of the
        // renderer's readiness. Include setup in error handling as well as fetch.
        state.closeCountry();
        controller.page.classList.add("has-country-drawer", "has-preset-editor");
        if (state.draft && !reload) { showDraft(controller); return; }
        state.groups.replaceChildren();
        preview(controller);
        if (id !== "new" && !/^[0-9a-f-]{36}$/i.test(id)) throw new Error("This preset link is invalid.");
        const response = await fetch(endpoint(controller, id), {signal: abort.signal, cache: "no-store"});
        if (!response.ok) throw new Error(response.status === 404 ? "This preset no longer exists." : "The preset could not be loaded.");
        const draft = await response.json();
        if (abort.signal.aborted || !state.active || state.id !== id) return;
        draft.groups = draft.groups.map(group => ({color: group.color, title: group.title || "", countries: group.countries.filter(code => controller.countriesByCode.has(code))}));
        if (!draft.groups.length) draft.groups.push({color: state.palette[0], title: "", countries: []});
        draft.activeGroup = 0;
        draft.dirty = false;
        state.drafts.set(id, draft);
        state.draft = draft;
        showDraft(controller);
    } catch (error) {
        if (error.name !== "AbortError" && state.active && state.id === id) {
            state.drawer.setAttribute("aria-busy", "false");
            state.status.textContent = "The preset editor could not be opened. Try loading it again.";
            if (error.message === "This preset no longer exists." || error.message === "This preset link is invalid.") state.status.textContent = error.message;
            state.retry.textContent = "Retry";
            state.retry.hidden = false;
        }
    }
}

export function selectPresetCountry(controller, code) {
    const state = controller.presetEditor;
    if (!state?.active) return false;
    if (!state.draft || state.fields.disabled) return true;
    const draft = state.draft;
    const assigned = draft.groups.findIndex(group => group.countries.includes(code));
    if (assigned !== -1) {
        draft.activeGroup = assigned;
    } else {
        const group = draft.groups[draft.activeGroup];
        if (!group) { state.status.textContent = "Add a color before selecting countries."; return true; }
        group.countries.push(code);
        markChanged(controller);
    }
    renderGroups(controller);
    return true;
}

function exit(controller, discard = false) {
    const state = controller.presetEditor;
    if (state.saving) return;
    if (discard) state.drafts.delete(state.id);
    const url = new URL(location.href);
    url.searchParams.delete("edit_preset");
    history.pushState({}, "", url);
    announceLocation();
    syncPresetEditor(controller);
    state.restoreCountry();
    state.refresh();
    controller.container.focus({preventScroll: true});
}

export function initializePresetMap(controller, callbacks) {
    const page = controller.page;
    const signal = controller.abortController.signal;
    const state = controller.presetEditor = {
        ...callbacks, active: false, id: null, drafts: new Map(), draft: null, preview: null, saving: false,
        drawer: page.querySelector("[data-preset-map-drawer]"), form: page.querySelector("[data-preset-map-form]"),
        fields: page.querySelector("[data-preset-map-fields]"), groups: page.querySelector("[data-preset-map-groups]"),
        status: page.querySelector("[data-preset-map-status]"), retry: page.querySelector("[data-preset-map-retry]"),
        countries: page.querySelector("[data-preset-map-countries]"), add: page.querySelector("[data-preset-map-add]"),
        countriesField: page.querySelector("[data-preset-map-countries-field]"), chips: page.querySelector("[data-preset-map-country-chips]"),
        count: page.querySelector("[data-preset-map-count]"), colorTemplate: page.querySelector("[data-preset-map-color-template]"),
        defaultColor: page.querySelector("[data-preset-map-default]"), save: page.querySelector("[data-preset-map-save]"),
        discard: page.querySelector("[data-preset-map-discard]"), close: page.querySelector("[data-preset-map-exit]"),
    };
    state.palette = [...state.colorTemplate.content.querySelectorAll("[data-map-color-choice]")].map(choice => choice.dataset.mapColorChoice);
    signal.addEventListener("abort", () => state.loadAbort?.abort(), {once: true});
    state.retry.addEventListener("click", async () => {
        if (state.saving) return;
        if (state.draft?.dirty && !await confirmAction({title: "Reload the saved preset?", message: "Unsaved color groups and country selections in this draft will be discarded.", accept: "Discard & reload"})) return;
        if (!signal.aborted && !state.saving) syncPresetEditor(controller, {reload: true});
    }, {signal});
    page.querySelector("[data-preset-map-exit]").addEventListener("click", () => exit(controller), {signal});
    page.querySelector("[data-preset-map-discard]").addEventListener("click", async () => {
        if (state.saving) return;
        if (state.draft?.dirty && !await confirmAction({title: "Discard this preset draft?", message: "Your unsaved colors and country selections will be lost. The saved preset stays unchanged.", accept: "Discard draft"})) return;
        if (!signal.aborted && !state.saving) exit(controller, true);
    }, {signal});
    state.add.addEventListener("click", () => {
        const draft = state.draft;
        if (!draft || state.fields.disabled) return;
        let color = state.palette.find(value => !draft.groups.some(group => group.color === value));
        let number = 0x123456 + draft.groups.length * 654321;
        while (!color || draft.groups.some(group => group.color === color)) {
            color = `#${(number++ & 0xffffff).toString(16).padStart(6, "0")}`;
        }
        draft.groups.push({color, title: "", countries: []});
        draft.activeGroup = draft.groups.length - 1;
        markChanged(controller);
        renderGroups(controller);
        const title = state.groups.lastElementChild.querySelector(".preset-map-group-title");
        title.focus({preventScroll: true});
        title.scrollIntoView({block: "nearest"});
    }, {signal});
    state.countries.addEventListener("change", event => {
        // Programmatic redraws synchronize the custom control without editing.
        if (state.rendering) return;
        const group = state.draft?.groups[state.draft.activeGroup];
        if (!group || state.fields.disabled) return;
        group.countries = [...state.countries.selectedOptions].map(option => option.value);
        markChanged(controller);
        renderGroups(controller);
    }, {signal});
    state.form.addEventListener("input", event => {
        if (!["name", "description"].includes(event.target.name) || !state.draft) return;
        state.draft[event.target.name] = event.target.value;
        markChanged(controller);
    }, {signal});
    state.form.addEventListener("submit", async event => {
        event.preventDefault();
        if (!state.draft || state.saving || !state.active) return;
        const draft = state.draft;
        const id = state.id;
        state.saving = true;
        setBusy(state, true);
        state.status.textContent = "Saving…";
        const finish = beginTask("Saving color preset…");
        try {
            const response = await fetch(endpoint(controller, id), {
                method: "POST", signal, headers: {"Content-Type": "application/json", "X-CSRFToken": page.querySelector('[name="csrfmiddlewaretoken"]').value},
                body: JSON.stringify({name: draft.name, description: draft.description, default_color: draft.default_color, updated_at: draft.updated_at, groups: draft.groups}),
            });
            const result = await response.json().catch(() => ({error: "The preset could not be saved. Try again."}));
            if (response.status === 409) {
                state.retry.textContent = "Reload";
                state.retry.hidden = false;
            }
            if (!response.ok) throw new Error(result.error || "The preset could not be saved.");
            draft.dirty = false;
            draft.id = result.id;
            draft.updated_at = result.updated_at;
            state.drafts.delete(id);
            state.drafts.set(result.id, draft);
            if (state.id === id) {
                state.id = result.id;
                if (state.active && !controller.suspended && location.pathname === "/") {
                    const url = new URL(location.href);
                    url.searchParams.set("edit_preset", result.id);
                    history.replaceState(history.state, "", url);
                    announceLocation();
                }
                state.status.textContent = "Saved";
                state.retry.hidden = true;
            }
            document.dispatchEvent(new CustomEvent("world-journal:map-preset-saved", {detail: {previousId: id, id: result.id}}));
            notify({id: "preset-save", kind: "success", title: "Color preset saved", message: "These colors are now active on the map."});
            state.refresh();
        } catch (error) {
            if (error.name !== "AbortError" && state.id === id) state.status.textContent = `${error.message} Your draft has been kept.`;
            if (error.name !== "AbortError") notify({id: "preset-save", kind: "error", title: "Preset could not be saved", message: `${error.message} Your draft has been kept.`});
        } finally {
            finish();
            state.saving = false;
            if (state.draft) setBusy(state, false);
        }
    }, {signal});
    window.addEventListener("beforeunload", event => {
        if (![...state.drafts.values()].some(draft => draft.dirty)) return;
        event.preventDefault();
        event.returnValue = "";
    }, {signal});
    syncPresetEditor(controller);
}
