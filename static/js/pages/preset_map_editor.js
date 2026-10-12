// Color groups are UI state; the database continues storing one color per country.
import { beginTask, confirmAction, notify } from "../notifications.js";
const COLORS = ["#4a90e2", "#dd6858", "#4aab83", "#a57bd5", "#d5ac47", "#52abb8", "#cf78a3"];
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
    state.status.textContent = "Unsaved changes · colors are a preview.";
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

function renderGroups(controller) {
    const state = controller.presetEditor;
    const draft = state.draft;
    state.rendering = true;
    state.groups.replaceChildren();
    draft.groups.forEach((group, index) => {
        const card = document.createElement("section");
        card.className = "preset-map-group";
        card.classList.toggle("is-active", index === draft.activeGroup);
        card.style.setProperty("--group-color", group.color);
        const heading = document.createElement("div");
        heading.className = "preset-map-group-heading";
        const choose = button(`${group.title?.trim() || `Color ${index + 1}`} · ${group.countries.length}`, "preset-map-group-select", () => {
            draft.activeGroup = index;
            renderGroups(controller);
        });
        choose.setAttribute("aria-pressed", String(index === draft.activeGroup));
        const color = document.createElement("input");
        color.type = "color";
        color.value = group.color;
        color.setAttribute("aria-label", `Change color ${index + 1}`);
        const originalColor = group.color;
        color.addEventListener("input", () => {
            group.color = color.value.toLowerCase();
            card.style.setProperty("--group-color", group.color);
            markChanged(controller);
        });
        color.addEventListener("change", () => {
            const same = draft.groups.find(other => other !== group && other.color === group.color);
            if (same) {
                const combinedTitle = [...new Set([same.title, group.title].map(title => (title || "").trim()).filter(Boolean))].join(" / ");
                if (combinedTitle.length > 160) {
                    group.color = originalColor;
                    color.value = originalColor;
                    card.style.setProperty("--group-color", originalColor);
                    preview(controller);
                    state.status.textContent = "Shorten the group titles before combining these colors (160 characters maximum).";
                    return;
                }
                same.title = combinedTitle;
                same.countries.push(...group.countries);
                draft.groups.splice(index, 1);
                draft.activeGroup = draft.groups.indexOf(same);
                state.status.textContent = "Groups with the same color were combined. Save to keep your changes.";
            } else draft.activeGroup = index;
            renderGroups(controller);
        });
        heading.append(choose, color, button("Remove", "preset-map-group-remove", async () => {
            if (group.countries.length && !await confirmAction({title: `Remove ${group.title?.trim() || "this color group"}?`, message: `This clears the color assigned to ${group.countries.length} countr${group.countries.length === 1 ? "y" : "ies"}. Save the preset afterward to keep the change.`, accept: "Remove group"})) return;
            if (!state.active || state.saving || state.draft !== draft || controller.abortController.signal.aborted) return;
            const active = draft.groups[draft.activeGroup];
            draft.groups.splice(draft.groups.indexOf(group), 1);
            draft.activeGroup = active !== group ? draft.groups.indexOf(active) : Math.max(0, Math.min(index, draft.groups.length - 1));
            markChanged(controller);
            renderGroups(controller);
        }));
        const titleLabel = document.createElement("label");
        titleLabel.className = "preset-map-group-title";
        titleLabel.textContent = "Title";
        const title = document.createElement("input");
        title.type = "text";
        title.maxLength = 160;
        title.value = group.title || "";
        title.placeholder = `Color ${index + 1}, e.g. Western aligned`;
        title.addEventListener("input", () => {
            group.title = title.value;
            choose.textContent = `${group.title.trim() || `Color ${index + 1}`} · ${group.countries.length}`;
            markChanged(controller);
        });
        titleLabel.append(title);
        const countries = document.createElement("div");
        countries.className = "preset-map-country-chips";
        for (const code of [...group.countries].sort((a, b) => controller.countriesByCode.get(a).name.localeCompare(controller.countriesByCode.get(b).name))) {
            const name = controller.countriesByCode.get(code).name;
            const remove = button(name, "preset-map-country-chip", () => {
                group.countries = group.countries.filter(value => value !== code);
                draft.activeGroup = index;
                markChanged(controller);
                renderGroups(controller);
            });
            remove.title = `Remove ${name} from this color`;
            remove.setAttribute("aria-label", `Remove ${name} from this color`);
            const close = document.querySelector('[data-control-icon="close"]');
            if (close) remove.append(close.content.cloneNode(true));
            countries.append(remove);
        }
        if (!group.countries.length) {
            const hint = document.createElement("p");
            hint.className = "field-note";
            hint.textContent = "Select this color, then click countries on the map.";
            countries.append(hint);
        }
        card.append(heading, titleLabel, countries);
        state.groups.append(card);
    });
    const current = draft.groups[draft.activeGroup];
    const otherCodes = new Set(draft.groups.filter(group => group !== current).flatMap(group => group.countries));
    state.countries.replaceChildren();
    for (const country of [...controller.countriesByCode.values()].sort((a, b) => a.name.localeCompare(b.name))) {
        const option = new Option(country.name, country.iso_a2, false, Boolean(current?.countries.includes(country.iso_a2)));
        option.disabled = otherCodes.has(country.iso_a2);
        state.countries.add(option);
    }
    state.countries.disabled = !current;
    state.add.disabled = draft.groups.length >= 238;
    // The native field is the source of truth for the shared custom selector.
    state.countries.dispatchEvent(new Event("change", {bubbles: true}));
    state.rendering = false;
}

function showDraft(controller) {
    const state = controller.presetEditor;
    const draft = state.draft;
    state.form.elements.name.value = draft.name;
    state.form.elements.description.value = draft.description;
    state.form.elements.default_color.value = draft.default_color;
    state.fields.disabled = state.saving;
    state.retry.hidden = true;
    state.status.textContent = draft.dirty ? "Unsaved changes · colors are a preview." : "Country selection mode · choose a color and click countries.";
    renderGroups(controller);
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
    state.fields.disabled = true;
    state.status.textContent = "Loading color preset…";
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
        if (!draft.groups.length) draft.groups.push({color: COLORS[0], title: "", countries: []});
        draft.activeGroup = 0;
        draft.dirty = false;
        state.drafts.set(id, draft);
        state.draft = draft;
        showDraft(controller);
    } catch (error) {
        if (error.name !== "AbortError" && state.active && state.id === id) {
            state.status.textContent = "The preset editor could not be opened. Try loading it again.";
            if (error.message === "This preset no longer exists." || error.message === "This preset link is invalid.") state.status.textContent = error.message;
            state.retry.textContent = "Retry loading";
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
        state.status.textContent = `${controller.countriesByCode.get(code).name} belongs to ${draft.groups[assigned].title?.trim() || `color ${assigned + 1}`}. That group is now selected.`;
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
    };
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
        let color = COLORS.find(value => !draft.groups.some(group => group.color === value));
        let number = 0x123456 + draft.groups.length * 654321;
        while (!color || draft.groups.some(group => group.color === color)) {
            color = `#${(number++ & 0xffffff).toString(16).padStart(6, "0")}`;
        }
        draft.groups.push({color, title: "", countries: []});
        draft.activeGroup = draft.groups.length - 1;
        markChanged(controller);
        renderGroups(controller);
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
        if (!["name", "description", "default_color"].includes(event.target.name) || !state.draft) return;
        state.draft[event.target.name] = event.target.value;
        markChanged(controller);
    }, {signal});
    state.form.addEventListener("submit", async event => {
        event.preventDefault();
        if (!state.draft || state.saving || !state.active) return;
        const draft = state.draft;
        const id = state.id;
        state.saving = true;
        state.fields.disabled = true;
        state.status.textContent = "Saving preset…";
        const finish = beginTask("Saving color preset…");
        try {
            const response = await fetch(endpoint(controller, id), {
                method: "POST", signal, headers: {"Content-Type": "application/json", "X-CSRFToken": page.querySelector('[name="csrfmiddlewaretoken"]').value},
                body: JSON.stringify({name: draft.name, description: draft.description, default_color: draft.default_color, updated_at: draft.updated_at, groups: draft.groups}),
            });
            const result = await response.json().catch(() => ({error: "The preset could not be saved. Try again."}));
            if (response.status === 409) {
                state.retry.textContent = "Discard draft & reload saved preset";
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
                state.status.textContent = "Saved · these colors are now active on the map.";
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
            if (state.draft) state.fields.disabled = false;
        }
    }, {signal});
    window.addEventListener("beforeunload", event => {
        if (![...state.drafts.values()].some(draft => draft.dirty)) return;
        event.preventDefault();
        event.returnValue = "";
    }, {signal});
    syncPresetEditor(controller);
}
