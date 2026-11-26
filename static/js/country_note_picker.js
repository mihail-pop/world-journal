import { notify } from "./notifications.js";

export function initializeCountryNotePicker() {
    const dialog = document.querySelector("[data-country-note-dialog]");
    let loadAbort = null;
    let active = null;

    function close() {
        dialog.close();
        document.documentElement.classList.remove("country-note-modal-open");
    }
    function show(markup) {
        const template = document.createElement("template");
        template.innerHTML = markup;
        if (!template.content.querySelector("[data-country-note-form]")) throw new Error("Note picker unavailable");
        dialog.replaceChildren(template.content);
    }
    function busy(value) {
        active.saving = value;
        dialog.setAttribute("aria-busy", String(value));
        for (const field of dialog.querySelectorAll("button, input")) field.disabled = value;
    }
    document.addEventListener("click", async event => {
        const opener = event.target.closest("[data-country-note-picker]");
        if (!opener || active?.saving) return;
        loadAbort?.abort();
        const abort = loadAbort = new AbortController();
        opener.disabled = true;
        try {
            const response = await fetch(opener.dataset.countryNotePicker, {signal: abort.signal, cache: "no-store"});
            if (!response.ok) throw new Error("Note picker unavailable");
            const markup = await response.text();
            if (abort.signal.aborted || !opener.isConnected) return;
            show(markup);
            active = {opener, saving: false};
            dialog.classList.toggle("is-map", Boolean(opener.closest(".page-map")));
            document.documentElement.classList.add("country-note-modal-open");
            dialog.showModal();
        } catch (error) {
            if (error.name !== "AbortError") notify({kind: "error", title: "Notes could not be loaded"});
        } finally {
            opener.disabled = false;
            if (loadAbort === abort) loadAbort = null;
        }
    });
    dialog.addEventListener("click", event => {
        if (active?.saving) return;
        if (event.target.closest("[data-country-note-close]")) close();
        else if (event.target === dialog) {
            const box = dialog.getBoundingClientRect();
            if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) close();
        }
    });
    dialog.addEventListener("cancel", event => {
        if (active?.saving) event.preventDefault();
    });
    dialog.addEventListener("close", () => {
        document.documentElement.classList.remove("country-note-modal-open");
        const opener = active?.opener.isConnected ? active.opener : [...document.querySelectorAll("[data-country-note-picker]")]
            .find(button => button.dataset.countryNotePicker === active?.opener.dataset.countryNotePicker);
        opener?.focus({preventScroll: true});
    });
    dialog.addEventListener("input", event => {
        if (!event.target.matches("[data-country-note-search]")) return;
        const normalize = text => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
        const query = normalize(event.target.value.trim());
        let found = false;
        for (const option of dialog.querySelectorAll("[data-country-note-option]")) {
            const empty = !option.querySelector("input").value;
            option.hidden = Boolean(query) && (empty || !normalize(option.textContent).includes(query));
            if (!option.hidden) found = true;
        }
        dialog.querySelector("[data-country-note-empty]").hidden = found;
    });
    dialog.addEventListener("submit", async event => {
        const form = event.target.closest("[data-country-note-form]");
        if (!form) return;
        event.preventDefault();
        if (active.saving) return;
        const body = new FormData(form);
        busy(true);
        try {
            const response = await fetch(form.action, {method: "POST", body});
            if (response.status === 400) {
                show(await response.text());
                notify({kind: "warning", title: "Choose an available note"});
                return;
            }
            if (!response.ok) throw new Error("Overview could not be saved");
            const result = await response.json();
            document.dispatchEvent(new CustomEvent("world-journal:country-overview-changed", {detail: result}));
            close();
            notify({kind: "success", title: "Overview note updated"});
        } catch (_) {
            notify({kind: "error", title: "Overview note could not be saved", message: "Please try again."});
        } finally {
            busy(false);
        }
    });
    document.addEventListener("world-journal:page-cleanup", () => { loadAbort?.abort(); close(); });
}
