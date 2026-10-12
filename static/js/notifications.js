// One feedback surface outside HTMX page swaps. Routine background work stays quiet.
const notices = new Map();
const requests = new WeakMap();
let registered = false;
let sequence = 0;
let dialogState = null;

function icon(name) {
    return document.querySelector(`[data-control-icon="${name}"]`).content.cloneNode(true);
}

export function dismissNotice(id) {
    const item = notices.get(id);
    if (!item) return;
    clearTimeout(item.timer);
    item.element.remove();
    notices.delete(id);
}

export function updateNotice(id, message) {
    const element = notices.get(id)?.element;
    if (element) element.querySelector(".notification-copy p").textContent = message;
}

export function notify({id = `notice-${++sequence}`, kind = "info", title, message = "", action, duration} = {}) {
    if (!["info", "success", "warning", "error", "loading"].includes(kind)) kind = "info";
    const rack = document.querySelector("[data-notification-rack]");
    if (!rack) return id;
    dismissNotice(id);
    while (notices.size >= 4) dismissNotice(notices.keys().next().value);
    const element = document.createElement("section");
    element.className = "app-notification";
    element.dataset.kind = kind;
    const badge = document.createElement("span");
    badge.className = "notification-icon";
    badge.setAttribute("aria-hidden", "true");
    if (kind === "loading") {
        const spinner = document.createElement("span");
        spinner.className = "notification-spinner";
        badge.append(spinner);
    } else badge.append(icon(kind === "success" ? "check" : "info"));
    const copy = document.createElement("div");
    copy.className = "notification-copy";
    copy.setAttribute("role", kind === "error" ? "alert" : "status");
    const heading = document.createElement("strong");
    heading.textContent = title || ({success: "Done", error: "Something needs attention", warning: "Please check", loading: "Working…", info: "World Journal"}[kind]);
    const text = document.createElement("p");
    text.textContent = message;
    copy.append(heading);
    if (message) copy.append(text);
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
    const close = document.createElement("button");
    close.type = "button";
    close.className = "notification-close";
    close.setAttribute("aria-label", "Dismiss notification");
    close.append(icon("close"));
    close.addEventListener("click", () => dismissNotice(id));
    element.append(badge, copy, close);
    const item = {element, timer: null};
    notices.set(id, item);
    rack.append(element);
    if (action?.href) window.htmx.process(element);
    const lifetime = duration ?? (["error", "loading"].includes(kind) || action ? 0 : kind === "warning" ? 12000 : 6000);
    const resume = () => { clearTimeout(item.timer); if (lifetime) item.timer = setTimeout(() => dismissNotice(id), lifetime); };
    element.addEventListener("mouseenter", () => clearTimeout(item.timer));
    element.addEventListener("mouseleave", resume);
    element.addEventListener("focusin", () => clearTimeout(item.timer));
    element.addEventListener("focusout", event => { if (!element.contains(event.relatedTarget)) resume(); });
    resume();
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
    document.querySelector("[data-action-dialog]").close();
    document.querySelector("[data-dialog-content]").replaceChildren();
    if (state.opener?.isConnected) state.opener.focus({preventScroll: true});
    state.resolve?.(accepted);
}

export function confirmAction({title, message, accept = "Delete", opener = document.activeElement, onAccept} = {}) {
    if (dialogState) return Promise.resolve(false);
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
    document.addEventListener("world-journal:preference-storage-error", () => notify({id: "preference-storage", kind: "warning", title: "Browser preferences could not be kept", message: "Your choice applies now, but may reset after a refresh. Allow local storage for this site to remember it."}));
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
            notify({id: "form-validation", kind: "warning", title: "A few details need attention", message: "Review the highlighted fields. Your changes have not been saved."});
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
            notify({id: "request-error", kind: "error", title: "The request could not be completed", message: event.detail.xhr.status === 403 ? "Your session may have expired. Reload the page before trying again; keep a copy of any unsaved text." : "Check that the server is running and try again. Your current page is kept."});
        }
    });
    document.body.addEventListener("htmx:afterSwap", event => {
        if (event.detail.target?.id === "app-content") dismissNotice("request-error");
    });
    for (const name of ["htmx:sendError", "htmx:timeout"]) document.body.addEventListener(name, event => {
        const config = event.detail.requestConfig;
        if (config?.verb === "get" && event.detail.target?.id !== "app-content") return;
        notify({id: "request-error", kind: "error", title: "Connection interrupted", message: "Check that World Journal is running, then try again. Your current page is kept."});
    });
}
