import { notify } from "../notifications.js";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const BASIS_KEY = "world-journal:journal-date-basis";

export function initializeJournalDates(state, changed, beforeRewind) {
    const {form, page} = state;
    const signal = state.events.signal;
    const fields = Object.fromEntries([...form.querySelectorAll("[data-journal-date-part]")].map(input => [input.dataset.journalDatePart, input]));
    const basis = form.elements.namedItem("date_basis");
    const basisButton = form.querySelector("[data-journal-date-basis]");
    const rewind = form.querySelector("[data-journal-rewind]");
    let dateTimer, rewindTimer, request;
    let running = false, generation = 0;
    let monthPrefix = "", monthTime = 0, monthIndex = -1;
    let restoredBasis = false;
    if (!new URL(location.href).searchParams.has("date_basis")) {
        try {
            const saved = localStorage.getItem(BASIS_KEY);
            if (["created", "updated"].includes(saved)) {
                restoredBasis = saved !== basis.value;
                basis.value = saved;
            }
        } catch (_) { /* The default still works when browser storage is unavailable. */ }
    }
    function monthValue() {
        const text = fields.month.value.trim();
        if (!text || /^\d+$/.test(text)) return text;
        const index = MONTHS.findIndex(name => name.toLowerCase().startsWith(text.toLowerCase()));
        return index < 0 ? text : String(index + 1);
    }
    function normalize(input, commit = false) {
        if (input === fields.month && /^[a-z]+$/i.test(input.value.trim())) {
            const number = Number(monthValue());
            if (number >= 1 && number <= 12) input.value = MONTHS[number - 1].slice(0, 3);
            return;
        }
        const digits = input.value.replace(/\D/g, "");
        if (input === fields.year) { input.value = digits.slice(0, 4); return; }
        const maximum = input === fields.month ? 12 : 31;
        let value = digits.slice(0, 2);
        if (digits && (Number(digits) > maximum || digits.length > 2)) value = String(Math.min(maximum, Number(digits)));
        if (commit && value && Number(value) === 0) value = "1";
        input.value = value;
    }
    function prepare() {
        const raw = {year: fields.year.value, month: monthValue(), day: fields.day.value};
        let valid = !((raw.year && (!/^\d{4}$/.test(raw.year) || Number(raw.year) < 1))
            || (raw.month && (!/^\d{1,2}$/.test(raw.month) || Number(raw.month) < 1 || Number(raw.month) > 12))
            || (raw.day && (!/^\d{1,2}$/.test(raw.day) || Number(raw.day) < 1 || Number(raw.day) > 31)));
        if (valid && raw.day) {
            const now = new Date();
            const year = Number(raw.year) || now.getFullYear(), month = Number(raw.month) || now.getMonth() + 1;
            const date = new Date(0);
            date.setUTCFullYear(year, month - 1, Number(raw.day));
            valid = date.getUTCFullYear() === year && date.getUTCMonth() + 1 === month && date.getUTCDate() === Number(raw.day);
        }
        for (const input of Object.values(fields)) {
            const invalid = !valid && Boolean(input.value);
            input.setCustomValidity(invalid ? "Enter a valid date. Use four digits for the year." : "");
            input.setAttribute("aria-invalid", String(invalid));
        }
        form.elements.namedItem("month").value = raw.month;
        rewind.disabled = !valid && !running;
        return valid;
    }
    function sync() {
        const updated = basis.value === "updated";
        basisButton.textContent = updated ? "Updated" : "Saved";
        basisButton.setAttribute("aria-label", updated ? "Filter by updated date" : "Filter by saved date");
        rewind.textContent = running ? "Stop" : "Rewind";
        rewind.setAttribute("aria-pressed", String(running));
        rewind.setAttribute("aria-label", running ? "Stop rewind" : "Rewind through matching days");
        prepare();
    }
    function stop() {
        running = false;
        generation++;
        clearTimeout(dateTimer);
        clearTimeout(rewindTimer);
        request?.abort();
        request = null;
        delete page.dataset.journalRewinding;
        sync();
        if (!signal.aborted) document.dispatchEvent(new CustomEvent("world-journal:news-content-ready"));
    }
    async function advance(token, before = "") {
        if (!running || token !== generation) return;
        const abort = request = new AbortController();
        const timeout = setTimeout(() => abort.abort(), 20000);
        const params = new URLSearchParams(new FormData(form));
        params.set("rewind", "1");
        if (before) params.set("rewind_before", before);
        try {
            const response = await fetch(`${form.action}?${params}`, {signal: abort.signal, cache: "no-store"});
            if (!response.ok) throw new Error("Rewind could not be loaded");
            const data = await response.json();
            if (!running || token !== generation) return;
            if (data.exhausted) { stop(); return; }
            const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(data.date || "");
            if (!parts || !data.html) throw new Error("Invalid rewind response");
            const template = document.createElement("template");
            template.innerHTML = data.html;
            const collection = template.content.querySelector("[data-journal-collection]");
            if (!collection) throw new Error("Invalid journal results");
            fields.year.value = parts[1];
            fields.month.value = MONTHS[Number(parts[2]) - 1].slice(0, 3);
            fields.day.value = parts[3];
            form.querySelector('[data-journal-extra-filter][name="date"]')?.remove();
            prepare();
            const results = page.querySelector("#journal-results");
            results.replaceChildren(template.content);
            window.htmx?.process(results);
            history.replaceState(history.state, "", data.url);
            document.dispatchEvent(new CustomEvent("world-journal:location-change"));
            document.dispatchEvent(new CustomEvent("world-journal:news-content-ready"));
            rewindTimer = setTimeout(() => advance(token, data.date), 2000);
        } catch (_) {
            if (running && token === generation) {
                stop();
                notify({kind: "error", title: "Rewind could not be loaded", message: "Please try again."});
            }
        } finally {
            clearTimeout(timeout);
            if (request === abort) request = null;
        }
    }
    function dateChanged(input) {
        stop();
        window.htmx?.trigger(form, "htmx:abort");
        normalize(input);
        form.querySelector('[data-journal-extra-filter][name="date"]')?.remove();
        if (!prepare()) return;
        dateTimer = setTimeout(changed, 250);
    }
    function selectMonth(letter) {
        const key = letter.toLowerCase(), now = Date.now();
        let prefix = now - monthTime < 1000 && monthPrefix && monthPrefix !== key ? monthPrefix + key : key;
        const matchesFor = text => MONTHS.map((name, index) => ({name, index})).filter(month => month.name.toLowerCase().startsWith(text));
        let matches = matchesFor(prefix);
        if (!matches.length) { prefix = key; matches = matchesFor(prefix); }
        if (!matches.length) return;
        const position = prefix === key && monthPrefix === key ? (matches.findIndex(month => month.index === monthIndex) + 1) % matches.length : 0;
        fields.month.value = matches[position].name.slice(0, 3);
        fields.month.select();
        monthPrefix = prefix; monthTime = now; monthIndex = matches[position].index;
    }
    for (const input of Object.values(fields)) {
        input.addEventListener("input", event => {
            if (event.isComposing) return;
            if (input === fields.month && /^[a-z]$/i.test(event.data || "")) selectMonth(event.data);
            dateChanged(input);
        }, {signal});
        input.addEventListener("blur", () => {
            const previous = input.value;
            normalize(input, true);
            if (input === fields.month) monthPrefix = "";
            if (input.value !== previous) dateChanged(input);
            prepare();
        }, {signal});
        input.addEventListener("keydown", event => {
            if (event.isComposing) return;
            if (input === fields.month && /^[a-z]$/i.test(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey) {
                event.preventDefault(); selectMonth(event.key); dateChanged(input); return;
            }
            if (event.key !== "Enter") return;
            event.preventDefault(); stop();
            Object.values(fields).forEach(field => normalize(field, true));
            if (prepare()) changed();
            else form.reportValidity();
        }, {signal});
    }
    basisButton.addEventListener("click", () => {
        stop();
        basis.value = basis.value === "updated" ? "created" : "updated";
        try { localStorage.setItem(BASIS_KEY, basis.value); } catch (_) { /* Use the selection for this page. */ }
        sync(); changed();
    }, {signal});
    rewind.addEventListener("click", () => {
        if (running) { stop(); return; }
        clearTimeout(dateTimer);
        if (!prepare()) { form.reportValidity(); return; }
        beforeRewind();
        window.htmx?.trigger(form, "htmx:abort");
        running = true;
        page.dataset.journalRewinding = "true";
        document.dispatchEvent(new CustomEvent("world-journal:news-content-ready"));
        sync();
        void advance(++generation);
    }, {signal});
    document.addEventListener("visibilitychange", () => { if (document.hidden && running) stop(); }, {signal});
    signal.addEventListener("abort", stop, {once: true});
    sync();
    return {prepare, sync, stop, restoredBasis, hasDate: Object.values(fields).some(input => input.value)};
}
