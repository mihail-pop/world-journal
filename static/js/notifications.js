// One feedback surface outside HTMX page swaps. Routine background work stays quiet.
const notices = new Map();
const requests = new WeakMap();
const retiring = new Set();
let registered = false;
let sequence = 0;
let dialogState = null;
let finishDialogExit = null;

export function dismissNotice(id) {
    const item = notices.get(id);
    if (!item) return;
    clearTimeout(item.timer);
    notices.delete(id);
    cancelAnimationFrame(item.frame);
    const element = item.element;
    if (!element.classList.contains("is-visible") || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        element.remove();
        return;
    }
    // Leave time for the exit transition, with a bounded number of retiring nodes.
    while (retiring.size >= 4) retiring.values().next().value.remove();
    const exit = {id, item, revive: () => {
        clearTimeout(exit.timer);
        element.removeEventListener("transitionend", onEnd);
        element.inert = false;
        element.removeAttribute("aria-hidden");
        element.classList.remove("is-leaving");
        retiring.delete(exit);
        return item;
    }, remove: () => {
        clearTimeout(exit.timer);
        element.removeEventListener("transitionend", onEnd);
        element.remove();
        retiring.delete(exit);
    }};
    const onEnd = event => { if (event.target === element && event.propertyName === "opacity") exit.remove(); };
    retiring.add(exit);
    element.inert = true;
    element.setAttribute("aria-hidden", "true");
    element.classList.add("is-leaving");
    element.addEventListener("transitionend", onEnd);
    exit.timer = setTimeout(exit.remove, 300);
}

export function updateNotice(id, message) {
    const element = notices.get(id)?.element;
    if (!element) return;
    let text = element.querySelector(".notification-copy p");
    if (!text) {
        text = document.createElement("p");
        element.querySelector(".notification-copy strong").after(text);
    }
    text.textContent = message;
}

export function notify({id = `notice-${++sequence}`, kind = "info", title, message = "", action, duration} = {}) {
    if (!["info", "success", "warning", "error", "loading"].includes(kind)) kind = "info";
    const rack = document.querySelector("[data-notification-rack]");
    if (!rack) return id;
    let item = notices.get(id);
    const previousExit = [...retiring].find(exit => exit.id === id);
    if (!item && previousExit) {
        item = previousExit.revive();
        while (notices.size >= 4) dismissNotice(notices.keys().next().value);
        notices.set(id, item);
    }
    if (!item) {
        while (notices.size >= 4) dismissNotice(notices.keys().next().value);
        item = {element: document.createElement("section"), timer: null, frame: null, lifetime: 0};
        item.element.className = "app-notification";
        const pause = () => clearTimeout(item.timer);
        item.resume = () => {
            clearTimeout(item.timer);
            if (item.lifetime && !item.element.matches(":hover, :focus-within")) item.timer = setTimeout(() => dismissNotice(id), item.lifetime);
        };
        item.element.addEventListener("mouseenter", pause);
        item.element.addEventListener("mouseleave", item.resume);
        item.element.addEventListener("focusin", pause);
        item.element.addEventListener("focusout", event => { if (!item.element.contains(event.relatedTarget)) queueMicrotask(item.resume); });
        notices.set(id, item);
        rack.append(item.element);
        item.frame = requestAnimationFrame(() => {
            item.frame = requestAnimationFrame(() => { if (notices.get(id) === item) item.element.classList.add("is-visible"); });
        });
    }
    const element = item.element;
    element.dataset.kind = kind;
    const copy = document.createElement("div");
    copy.className = "notification-copy";
    copy.setAttribute("role", kind === "error" ? "alert" : "status");
    copy.setAttribute("aria-atomic", "true");
    const heading = document.createElement("strong");
    // Server messages already describe the action; avoid a generic second heading.
    heading.textContent = title || message || ({success: "Saved", error: "Action failed", warning: "Action needed", loading: "Loading…", info: "Updated"}[kind]);
    const text = document.createElement("p");
    text.textContent = message;
    copy.append(heading);
    if (title && message && message !== title) copy.append(text);
    if (action) {
        const button = document.createElement(action.href ? "a" : "button");
        if (action.href) {
            button.href = action.href;
            button.setAttribute("hx-get", action.href);
            button.setAttribute("hx-target", "#app-content");
            button.setAttribute("hx-push-url", "true");
            button.setAttribute("hx-swap", "innerHTML show:top");
        } else button.type = "button";
        button.className = "notification-action";
        button.textContent = action.label;
        // Keep a navigation link mounted until HTMX captures its click.
        button.addEventListener("click", () => { if (!action.href) { dismissNotice(id); action.run(); } });
        copy.append(button);
    }
    element.replaceChildren(copy);
    if (action?.href) window.htmx.process(element);
    item.lifetime = duration ?? (kind === "loading" || action?.run ? 0 : kind === "error" ? 12000 : kind === "warning" || action ? 10000 : kind === "success" ? 4500 : 6000);
    item.resume();
    return id;
}

// Delay progress feedback so quick actions don't flash a popup.
export function beginTask(title, {id = `task-${++sequence}`, message = ""} = {}) {
    const timer = setTimeout(() => notify({id, kind: "loading", title, message}), 800);
    return () => { clearTimeout(timer); dismissNotice(id); };
}

function finishDialog(accepted = false) {
    if (!dialogState) return;
    const state = dialogState;
    dialogState = null;
    const dialog = document.querySelector("[data-action-dialog]");
    dialog.classList.add("is-leaving");
    const close = () => {
        clearTimeout(timer);
        dialog.close();
        dialog.classList.remove("is-leaving");
        document.querySelector("[data-dialog-content]").replaceChildren();
        finishDialogExit = null;
        if (state.opener?.isConnected) state.opener.focus({preventScroll: true});
        state.resolve?.(accepted);
    };
    const timer = setTimeout(close, window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 220);
    finishDialogExit = close;
}

export function confirmAction({title, message, accept = "Delete", opener = document.activeElement, onAccept} = {}) {
    if (dialogState) return Promise.resolve(false);
    finishDialogExit?.();
    const dialog = document.querySelector("[data-action-dialog]");
    document.querySelector("#action-dialog-title").textContent = title;
    document.querySelector("#action-dialog-description").textContent = message;
    const button = dialog.querySelector("[data-dialog-accept]");
    button.textContent = accept;
    button.disabled = false;
    dialog.querySelector("[data-dialog-error]")?.remove();
    return new Promise(resolve => {
        dialogState = {opener, resolve, onAccept};
        dialog.showModal();
    });
}

function showDeletion(fragment, url, opener) {
    if (dialogState?.form) finishDialog();
    if (dialogState) return;
    const form = fragment.querySelector("form");
    form.setAttribute("action", url);
    form.setAttribute("hx-post", url);
    form.setAttribute("hx-target", "#app-content");
    form.setAttribute("hx-push-url", "false");
    form.setAttribute("hx-swap", "innerHTML show:top");
    form.dataset.taskLabel = "Deleting…";
    // The dialog's explicit Delete button supplies the server's required consent.
    const consent = form.querySelector('[name="confirm"]');
    consent.type = "hidden";
    consent.value = "on";
    consent.required = false;
    const hiddenForm = document.createElement("div");
    hiddenForm.hidden = true;
    hiddenForm.append(form);
    confirmAction({title: fragment.querySelector("h1").textContent, message: fragment.querySelector("[data-confirm-description]").textContent, opener, onAccept: () => {
        if (!dialogState || dialogState.pending) return;
        dialogState.pending = true;
        const button = document.querySelector("[data-dialog-accept]");
        button.disabled = true;
        button.textContent = "Deleting…";
        form.requestSubmit();
    }});
    dialogState.form = form;
    document.querySelector("[data-dialog-content]").append(hiddenForm);
    window.htmx.process(form);
}

function deliver(notices) {
    for (const notice of notices || []) notify(notice);
}

export function registerNotifications() {
    if (registered) return;
    registered = true;
    deliver(JSON.parse(document.querySelector("#app-notices").textContent));
    document.addEventListener("world-journal:server-notices", event => deliver(event.detail.notices));
    document.addEventListener("world-journal:preferences-saved", () => {
        dismissNotice("preference-storage");
        notify({id: "preferences-saved", kind: "success", title: "Preferences saved"});
    });
    document.addEventListener("world-journal:preference-storage-error", () => {
        dismissNotice("preferences-saved");
        notify({id: "preference-storage", kind: "warning", title: "Browser preferences could not be kept", message: "Your choice applies now, but may reset after a refresh. Allow local storage for this site to remember it."});
    });
    const dialog = document.querySelector("[data-action-dialog]");
    dialog.addEventListener("cancel", event => {
        event.preventDefault();
        if (!dialogState?.pending) finishDialog();
    });
    dialog.addEventListener("click", event => {
        if (event.target.closest("[data-dialog-cancel]") && !dialogState?.pending) finishDialog();
        if (event.target.closest("[data-dialog-accept]")) {
            if (dialogState?.onAccept) dialogState.onAccept();
            else finishDialog(true);
        }
    });
    document.body.addEventListener("htmx:confirm", event => {
        const form = event.detail.elt.closest?.("form");
        if (!form) return;
        const removal = /\/settings\/news\/custom\/[^/]+\/remove\/$/.test(new URL(form.getAttribute("action") || location.href, location.href).pathname);
        if (!form.dataset.confirmTitle && !removal) return;
        event.preventDefault();
        const title = form.dataset.confirmTitle || `${form.querySelector('button').getAttribute('aria-label') || "Remove this source"}?`;
        const message = form.dataset.confirmMessage || (form.closest(".source-feed-row") ? "This feed will be removed. Entries saved to Journal are kept." : "This source and its feeds will be removed. Entries saved to Journal are kept.");
        confirmAction({title, message, accept: form.dataset.confirmAccept || "Remove"}).then(accepted => {
            if (accepted && form.isConnected) event.detail.issueRequest(true);
        });
    });
    document.body.addEventListener("htmx:beforeSwap", event => {
        if (event.detail.target?.id !== "app-content" || event.detail.isError) return;
        const html = event.detail.serverResponse || "";
        const response = /data-confirmation|errorlist/.test(html) ? new DOMParser().parseFromString(html, "text/html") : null;
        const confirmation = response?.querySelector("[data-confirmation]");
        if (confirmation) {
            event.detail.shouldSwap = false;
            event.stopImmediatePropagation();
            const url = event.detail.xhr.responseURL;
            showDeletion(confirmation, url, event.detail.requestConfig?.elt || document.activeElement);
            return;
        }
        if (dialogState?.form) finishDialog(true);
        if (event.detail.requestConfig?.verb !== "get" && response?.querySelector(".errorlist")) {
            notify({id: "form-validation", kind: "warning", title: "Check the highlighted fields", message: "Changes haven’t been saved."});
        }
    });
    document.body.addEventListener("htmx:beforeRequest", event => {
        const form = event.detail.elt.closest?.("form");
        if (!form || event.detail.requestConfig?.verb === "get") return;
        const path = new URL(form.getAttribute("action") || location.href, location.href).pathname;
        let label = form.dataset.taskLabel;
        if (!label && path.startsWith("/settings/news/")) label = path.endsWith("/remove/") ? "Removing source…" : "Checking source…";
        if (!label && path.startsWith("/settings/backup")) label = form.elements.namedItem("action")?.value === "preview" ? "Reading backup…" : form.elements.namedItem("action")?.value === "confirm" ? "Importing backup…" : null;
        if (!label && path.startsWith("/journal/")) label = form.enctype === "multipart/form-data" ? "Uploading image…" : "Saving to Journal…";
        if (!label && path.startsWith("/countries/")) label = "Saving changes…";
        if (label) requests.set(event.detail.xhr, beginTask(label));
    });
    document.body.addEventListener("htmx:afterRequest", event => {
        requests.get(event.detail.xhr)?.();
        requests.delete(event.detail.xhr);
        if (dialogState?.form === event.detail.elt && event.detail.xhr.getResponseHeader("HX-Location")) finishDialog(true);
        if (dialogState?.form === event.detail.elt) {
            dialogState.pending = false;
            dialog.querySelector("[data-dialog-accept]").disabled = false;
            dialog.querySelector("[data-dialog-accept]").textContent = "Delete";
            if (event.detail.failed || event.detail.xhr.status === 0) {
                let error = dialog.querySelector("[data-dialog-error]");
                if (!error) {
                    error = document.createElement("p");
                    error.dataset.dialogError = "";
                    error.setAttribute("role", "alert");
                    dialog.querySelector("[data-dialog-content]").append(error);
                }
                error.textContent = "Deletion could not be confirmed. Check your connection and try again, or cancel.";
            }
        }
        const config = event.detail.requestConfig;
        const meaningful = config?.verb !== "get" || event.detail.target?.id === "app-content";
        if (event.detail.failed && meaningful && event.detail.xhr.status !== 0) {
            notify({id: "request-error", kind: "error", title: "Request failed", message: event.detail.xhr.status === 403 ? "Copy any unsaved text, reload the page, then retry." : "Check that the server is running, then retry."});
        }
    });
    document.body.addEventListener("htmx:afterSwap", event => {
        if (event.detail.target?.id === "app-content") dismissNotice("request-error");
    });
    for (const name of ["htmx:sendError", "htmx:timeout"]) document.body.addEventListener(name, event => {
        const config = event.detail.requestConfig;
        if (config?.verb === "get" && event.detail.target?.id !== "app-content") return;
        notify({id: "request-error", kind: "error", title: "Connection interrupted", message: "Check that World Journal is running, then retry."});
    });
}
