import { confirmAction, dismissNotice, notify } from "../notifications.js";

let registered = false;
let active = null;
let searchTimer = null;

function closeCollection() {
    active?.dialog.close();
    document.documentElement.classList.remove("journal-modal-open");
}

function cleanup() {
    clearTimeout(searchTimer);
    searchTimer = null;
    closeCollection();
    active?.events.abort();
    active = null;
}

function syncControls(state) {
    const {page, form, collections} = state;
    const selected = form.elements.namedItem("collection").value;
    for (const button of form.querySelectorAll("[data-journal-select-collection]")) {
        if (button.dataset.journalSelectCollection === selected) button.setAttribute("aria-current", "page");
        else button.removeAttribute("aria-current");
    }
    for (const [name, attribute] of [["year", "journalYear"], ["month", "journalMonth"]]) {
        for (const button of form.querySelectorAll(`[data-journal-${name}]`)) {
            button.setAttribute("aria-pressed", String(button.dataset[attribute] === form.elements.namedItem(name).value));
        }
    }
    page.querySelector("[data-journal-collection-edit]").hidden = !collections[selected];
    const link = page.querySelector("[data-journal-new]");
    const url = new URL(link.href);
    if (selected) url.searchParams.set("collection", selected);
    else url.searchParams.delete("collection");
    link.href = url.pathname + url.search;
    form.querySelector("[data-journal-clear-filters]").hidden = ![...new FormData(form)]
        .some(([name, value]) => !["collection", "sort", "order"].includes(name) && String(value).trim());
}

function submit(state) {
    clearTimeout(searchTimer);
    searchTimer = null;
    if (!state?.form.isConnected) return;
    syncControls(state);
    state.form.requestSubmit();
}

function openCollection(edit, opener) {
    if (!active || active.dialog.open) return;
    const {form: filters, dialog, collections} = active;
    const data = edit ? collections[filters.elements.namedItem("collection").value] : null;
    if (edit && !data) return;
    const form = dialog.querySelector("[data-journal-collection-form]");
    form.reset();
    for (const error of form.querySelectorAll(".errorlist")) error.remove();
    for (const field of form.querySelectorAll("[aria-invalid]")) {
        field.removeAttribute("aria-invalid");
        field.removeAttribute("aria-describedby");
    }
    form.elements.namedItem("collection_id").value = data?.id || "";
    form.elements.namedItem("name").value = data?.name || "";
    form.elements.namedItem("description").value = data?.description || "";
    form.elements.namedItem("position").value = data?.position ?? 0;
    form.elements.namedItem("return_query").value = new URLSearchParams(new FormData(filters)).toString();
    const remove = form.querySelector("[data-journal-collection-delete]");
    remove.hidden = !data;
    remove.dataset.deleteUrl = data?.delete_url || "";
    dialog.querySelector("#journal-collection-dialog-title").textContent = edit ? "Edit collection" : "New collection";
    active.opener = opener;
    dialog.showModal();
    document.documentElement.classList.add("journal-modal-open");
    form.elements.namedItem("name").focus({preventScroll: true});
}

function initialize() {
    const page = document.querySelector("[data-journal-list]");
    cleanup();
    if (!page) return;
    const dialog = page.querySelector("[data-journal-collection-dialog]");
    if (dialog.open) dialog.close();
    const state = {page, dialog, form: page.querySelector("[data-journal-filters]"),
        collections: JSON.parse(page.querySelector("#journal-collection-data").textContent), events: new AbortController()};
    active = state;
    dialog.addEventListener("close", () => {
        document.documentElement.classList.remove("journal-modal-open");
        if (state.opener?.isConnected) state.opener.focus({preventScroll: true});
    }, {signal: state.events.signal});
    dialog.addEventListener("click", event => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeCollection();
    }, {signal: state.events.signal});
    syncControls(state);
    if (page.dataset.collectionModal) {
        openCollection(page.dataset.collectionModal === "edit", page.querySelector("[data-journal-collection-new]"));
        page.dataset.collectionModal = "";
        const url = new URL(location.href);
        url.searchParams.delete("create_collection");
        url.searchParams.delete("edit_collection");
        history.replaceState(history.state, "", url.pathname + url.search);
        document.dispatchEvent(new CustomEvent("world-journal:location-change"));
    }
}

export function registerJournalList() {
    if (registered) return;
    registered = true;
    document.addEventListener("world-journal:page-ready", initialize);
    document.addEventListener("world-journal:page-cleanup", cleanup);
    document.addEventListener("input", event => {
        if (!active || !event.target.matches("[data-journal-search]") || event.isComposing) return;
        clearTimeout(searchTimer);
        const state = active;
        searchTimer = setTimeout(() => submit(state), 300);
    });
    document.addEventListener("compositionend", event => {
        if (event.target.matches("[data-journal-search]")) event.target.dispatchEvent(new Event("input", {bubbles: true}));
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Enter" && !event.isComposing && event.target.matches("[data-journal-search]")) {
            event.preventDefault();
            submit(active);
        }
    });
    document.addEventListener("change", event => {
        if (!active || !event.target.matches("[data-journal-filters] select")) return;
        if (event.target.name === "sort") {
            for (const input of active.form.querySelectorAll('[data-journal-extra-filter][name="date_basis"]')) input.remove();
        }
        submit(active);
    });
    document.addEventListener("submit", event => {
        if (!event.target.matches("[data-journal-filters]")) return;
        clearTimeout(searchTimer);
        searchTimer = null;
        if (active) syncControls(active);
    }, true);
    document.addEventListener("invalid", event => {
        if (event.target.closest("[data-journal-collection-form]")) notify({id: "collection-validation", kind: "warning", title: "Check the collection details"});
    }, true);
    document.addEventListener("click", async event => {
        if (!active) return;
        const {form} = active;
        const add = event.target.closest("[data-journal-collection-new]");
        const edit = event.target.closest("[data-journal-collection-edit]");
        if (add || edit) { openCollection(Boolean(edit), add || edit); return; }
        if (event.target.closest("[data-journal-collection-close]")) { closeCollection(); return; }
        const remove = event.target.closest("[data-journal-collection-delete]");
        if (remove) {
            const accepted = await confirmAction({title: "Delete this collection?", message: "Its items will stay in the journal and return to their automatic collections.", accept: "Delete", opener: remove});
            if (!accepted || !remove.isConnected) return;
            remove.disabled = true;
            try {
                await window.htmx.ajax("POST", remove.dataset.deleteUrl, {target: "#app-content", swap: "innerHTML show:top",
                    values: {confirm: "on", csrfmiddlewaretoken: remove.form.elements.namedItem("csrfmiddlewaretoken").value}});
            } catch { /* Shared notifications report request failures. */ }
            finally { remove.disabled = false; }
            return;
        }
        const collection = event.target.closest("[data-journal-select-collection]");
        if (collection) form.elements.namedItem("collection").value = collection.dataset.journalSelectCollection;
        const year = event.target.closest("[data-journal-year]");
        const month = event.target.closest("[data-journal-month]");
        if (year || month) {
            const name = year ? "year" : "month";
            const field = form.elements.namedItem(name);
            const value = year ? year.dataset.journalYear : month.dataset.journalMonth;
            field.value = field.value === value ? "" : value;
            for (const input of form.querySelectorAll('[data-journal-extra-filter][name="date"], [data-journal-extra-filter][name="date_basis"]')) input.remove();
        }
        const order = event.target.closest("[data-journal-sort-order]");
        if (order) {
            const field = form.elements.namedItem("order");
            field.value = field.value === "asc" ? "desc" : "asc";
            order.dataset.order = field.value;
            order.title = field.value === "asc" ? "Ascending" : "Descending";
            order.setAttribute("aria-label", `Sort ${field.value === "asc" ? "ascending" : "descending"}`);
        }
        const clear = event.target.closest("[data-journal-clear-filters]");
        if (clear) {
            for (const name of ["q", "type", "year", "month"]) {
                const field = form.elements.namedItem(name);
                field.value = "";
                field.dispatchEvent(new Event("change"));
            }
            for (const input of form.querySelectorAll("[data-journal-extra-filter]")) input.remove();
        }
        if (collection || year || month || order || clear) submit(active);
    });
    document.body.addEventListener("htmx:afterSettle", event => {
        if (event.detail.target?.id === "journal-results") document.dispatchEvent(new CustomEvent("world-journal:location-change"));
    });
    document.body.addEventListener("htmx:beforeRequest", event => {
        if (event.detail.elt?.matches("[data-journal-filters]")) dismissNotice("journal-filters-error");
        if (event.detail.elt?.matches("[data-journal-collection-form]")) dismissNotice("collection-validation");
    });
    for (const name of ["htmx:responseError", "htmx:sendError", "htmx:timeout"]) {
        document.body.addEventListener(name, event => {
            if (event.detail.elt?.matches("[data-journal-filters]")) notify({id: "journal-filters-error", kind: "error", title: "Journal could not be loaded", message: "Your current items are still shown. Check the connection and try again."});
        });
    }
}
