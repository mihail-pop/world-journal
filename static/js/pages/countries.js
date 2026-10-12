import { getCountryFeed, prioritizeCountryFeed, rememberCountryFeed } from "../news_cache.js";
import { replaceCountryMarkup } from "../news_archive.js";
import { notify } from "../notifications.js";

let controller = null;
let registered = false;
const sections = ["overview", "articles", "videos", "notes"];
const normalize = value => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
const collator = new Intl.Collator(undefined, {sensitivity:"base", numeric:true});
const alive = state => controller === state && !state.abort.signal.aborted && !state.suspended && state.page.isConnected;

function directoryUrl(state, code = state.code, tab = state.tab) {
    const url = new URL("/countries/", location.origin);
    if (code) url.searchParams.set("country", code);
    if (tab !== "overview") url.searchParams.set("tab", tab);
    if (state.form.elements.q.value) url.searchParams.set("q", state.form.elements.q.value);
    if (state.form.elements.sort.value !== "name") url.searchParams.set("sort", state.form.elements.sort.value);
    if (state.form.elements.order.value !== "asc") url.searchParams.set("order", state.form.elements.order.value);
    return url.pathname + url.search;
}

function rememberLocation(state, replace = false) {
    const url = directoryUrl(state);
    if (url !== location.pathname + location.search) history[replace ? "replaceState" : "pushState"]({worldJournalCountries:true}, "", url);
    document.dispatchEvent(new CustomEvent("world-journal:location-change"));
}

function countryRow(state, country, favorite) {
    const key = `${favorite ? "favorite" : "all"}:${country.iso_a2}`;
    let node = state.rows.get(key);
    if (!node) {
        node = state.page.querySelector("[data-directory-row-template]").content.firstElementChild.cloneNode(true);
        const link = node.querySelector("a");
        link.dataset.directoryCountry = country.iso_a2;
        node.querySelector("[data-row-name]").textContent = country.name;
        node.querySelector("img").src = `https://flagcdn.com/${country.iso_a2.toLowerCase()}.svg`;
        node.querySelector("[data-flag-fallback]").textContent = country.flag;
        state.rows.set(key,node);
    }
    const link = node.querySelector("a");
    link.href = directoryUrl(state,country.iso_a2);
    if (state.code === country.iso_a2) link.setAttribute("aria-current","true");
    else link.removeAttribute("aria-current");
    const sort = state.form.elements.sort.value;
    node.querySelector("[data-row-value]").textContent = sort === "name" ? "" : country[sort] === null
        ? (sort === "area" ? "No area figure" : "No population figure")
        : `${country[sort+"_display"]}${sort === "area" ? " km²" : ""}`;
    return node;
}

function renderLists(state) {
    const focused = document.activeElement;
    const query = normalize(state.form.elements.q.value.trim());
    const sort = state.form.elements.sort.value;
    const direction = state.form.elements.order.value === "desc" ? -1 : 1;
    const matching = state.catalog.filter(country => normalize(`${country.name} ${country.iso_a2} ${country.iso_a3}`).includes(query));
    matching.sort((a,b) => {
        const names = collator.compare(a.name,b.name) || a.iso_a2.localeCompare(b.iso_a2);
        if (sort === "name") return names*direction;
        if (a[sort] === null || b[sort] === null) return a[sort] === b[sort] ? names : a[sort] === null ? 1 : -1;
        return (a[sort]-b[sort])*direction || names;
    });
    const favorites = matching.filter(country => state.favorites.has(country.iso_a2));
    state.page.querySelector("[data-directory-all-list]").replaceChildren(...matching.map(country => countryRow(state,country,false)));
    state.page.querySelector("[data-directory-favorite-list]").replaceChildren(...favorites.map(country => countryRow(state,country,true)));
    state.page.querySelector("[data-directory-favorites]").hidden = !state.favorites.size;
    state.page.querySelector("[data-directory-favorites-empty]").hidden = Boolean(favorites.length);
    state.page.querySelector("[data-directory-empty]").hidden = Boolean(matching.length);
    state.page.querySelector("[data-directory-count]").textContent = matching.length;
    for (const link of state.page.querySelectorAll("[data-directory-tab]")) link.href = directoryUrl(state,state.code,link.dataset.directoryTab);
    if (focused?.isConnected && focused.closest("[data-directory-lists]")) focused.focus({preventScroll:true});
}

function favoriteControl(state) {
    const favored = state.favorites.has(state.code);
    const button = state.page.querySelector("[data-directory-favorite]");
    button.setAttribute("aria-pressed",String(favored));
    button.setAttribute("aria-label",favored ? "Remove country from favorites" : "Add country to favorites");
    button.title = favored ? "Remove from favorites" : "Add to favorites";
    button.disabled = !state.code || state.favoritePending.has(state.code);
    state.favoriteForm.elements.favorite.value = favored ? "0" : "1";
}

function cancelLoad(state) {
    clearTimeout(state.timer);
    state.requestId++;
    state.contentAbort?.abort();
    state.contentAbort = null;
}

function renderContent(state, entry) {
    const key = `${state.code}:${state.tab}`;
    if (state.renderedKey === key && state.renderedMarkup === entry.markup) {
        state.content.setAttribute("aria-busy",String(Boolean(entry.pending)));
        return;
    }
    const scroll = state.content.scrollTop;
    const filter = state.content.querySelector('[data-news-filter][aria-pressed="true"]')?.dataset.newsFilter || "all";
    replaceCountryMarkup(state.content,entry.markup);
    state.renderedKey = key;
    state.renderedMarkup = entry.markup;
    state.content.setAttribute("aria-busy",String(Boolean(entry.pending)));
    state.content.scrollTop = scroll;
    applyArticleFilter(state,filter);
    window.htmx?.process(state.content);
}

function applyArticleFilter(state, filter) {
    const buttons = [...state.content.querySelectorAll("[data-news-filter]")];
    if (!buttons.some(button => button.dataset.newsFilter === filter)) filter = "all";
    for (const button of buttons) button.setAttribute("aria-pressed",String(button.dataset.newsFilter === filter));
    for (const section of state.content.querySelectorAll("[data-news-section]")) section.hidden = filter !== "all" && section.dataset.newsSection !== filter;
}

function showMessage(state, message, retry = false) {
    state.renderedKey = null;
    state.renderedMarkup = null;
    const paragraph = document.createElement("p");
    paragraph.className = "country-news-message";
    paragraph.textContent = message;
    state.content.replaceChildren(paragraph);
    if (retry) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "journal-button";
        button.dataset.directoryRetry = "";
        button.textContent = "Retry";
        state.content.append(button);
    }
}

function loadContent(state, retry = false) {
    cancelLoad(state);
    if (!state.code || !alive(state)) return;
    const {code,tab,requestId} = state;
    const feed = tab === "articles" || tab === "videos";
    if (feed) prioritizeCountryFeed(code);
    const cached = feed ? getCountryFeed(code,tab) : state.cache.get(`${code}:${tab}`);
    if (cached) { renderContent(state,cached); if (!retry) return; }
    else {
        // Keep the same country's old notes visible while refreshing after a
        // Journal edit, so returning to the page preserves its reading position.
        if (state.renderedKey !== `${code}:${tab}`) showMessage(state,`Loading ${tab} for ${state.byCode.get(code).name}…`);
        state.content.setAttribute("aria-busy","true");
    }
    // Coalesce quick selections without queuing a request for every country.
    state.timer = setTimeout(async () => {
        const abort = state.contentAbort = new AbortController();
        const requestedAt = Date.now();
        const correct = () => alive(state) && state.code === code && state.tab === tab && state.requestId === requestId;
        try {
            const endpoint = {overview:"countryFactsUrlTemplate",articles:"countryNewsUrlTemplate",videos:"countryVideosUrlTemplate",notes:"countryNotesUrlTemplate"}[tab];
            const url = new URL(state.page.dataset[endpoint].replace("COUNTRY_CODE",code),location.origin);
            if (retry && feed) url.searchParams.set("refresh","failed");
            const response = await fetch(url,{signal:abort.signal,cache:"no-store"});
            if (!response.ok) throw new Error("Country details unavailable");
            const markup = await response.text();
            if (!correct()) return;
            let entry;
            if (feed) entry = rememberCountryFeed(code,tab,markup,{requestedAt,version:response.headers.get("X-Feed-Version"),notify:false});
            else {
                const template = document.createElement("template");
                template.innerHTML = markup;
                const attribute = tab === "overview" ? "data-country-overview-result" : "data-country-notes-result";
                if (template.content.querySelector(`[${attribute}]`)?.getAttribute(attribute) !== code) throw new Error("Incorrect country response");
                entry = {markup};
                state.cache.set(`${code}:${tab}`,entry);
            }
            renderContent(state,entry);
        } catch (error) {
            if (error.name !== "AbortError" && correct()) {
                if (!cached) showMessage(state,`The ${tab} could not be loaded.`,true);
                state.content.setAttribute("aria-busy","false");
            }
        } finally {
            if (state.contentAbort === abort) state.contentAbort = null;
        }
    },180);
}

function select(state, code, tab = state.tab, {historyChange = true} = {}) {
    if (code && !state.byCode.has(code)) code = "";
    if (!sections.includes(tab)) tab = "overview";
    const changed = state.code !== code || state.tab !== tab;
    state.code = code;
    state.tab = tab;
    state.page.dataset.selectedCountry = code;
    state.page.dataset.selectedTab = tab;
    state.form.elements.country.value = code;
    state.form.elements.tab.value = tab;
    state.page.querySelector("[data-directory-detail]").hidden = !code;
    state.page.querySelector("[data-directory-welcome]").hidden = Boolean(code);
    for (const link of state.page.querySelectorAll("[data-directory-tab]")) {
        if (link.dataset.directoryTab === tab) link.setAttribute("aria-current","page");
        else link.removeAttribute("aria-current");
    }
    if (code) {
        const country = state.byCode.get(code);
        const name = state.page.querySelector("[data-directory-name]");
        name.textContent = country.name;
        name.href = `/journal/?country=${code}`;
        state.page.querySelector("[data-directory-region]").textContent = country.region;
        state.page.querySelector("[data-directory-subregion]").textContent = country.subregion;
        state.page.querySelector("[data-directory-map-link]").href = `/?country=${code}`;
        const flag = state.page.querySelector("[data-directory-detail-flag]");
        flag.hidden = false;
        flag.parentElement.querySelector("[data-flag-fallback]").hidden = true;
        flag.parentElement.querySelector("[data-flag-fallback]").textContent = country.flag;
        flag.src = `https://flagcdn.com/${code.toLowerCase()}.svg`;
        state.favoriteForm.action = state.page.dataset.favoriteUrlTemplate.replace("COUNTRY_CODE",code);
    }
    if (changed) {
        state.page.querySelector("[data-directory-favorite-status]").textContent = "";
        state.content.scrollTop = 0;
        loadContent(state);
    }
    favoriteControl(state);
    renderLists(state);
    if (historyChange) rememberLocation(state);
}

async function refreshFavorites(state) {
    const id = ++state.favoriteLoadId;
    try {
        const response = await fetch(state.page.dataset.personalUrl,{signal:state.abort.signal,cache:"no-store"});
        if (!response.ok) return;
        const result = await response.json();
        if (!alive(state) || id !== state.favoriteLoadId || state.favoritePending.size) return;
        state.favorites = new Set(result.favorites);
        favoriteControl(state);
        renderLists(state);
    } catch (_) { /* Already rendered favorites remain available offline. */ }
}

async function toggleFavorite(state) {
    const code = state.code;
    if (!code || state.favoritePending.has(code)) return;
    const url = state.page.dataset.favoriteUrlTemplate.replace("COUNTRY_CODE",code);
    state.favoriteLoadId++;
    state.favoritePending.add(code);
    favoriteControl(state);
    try {
        const response = await fetch(url,{method:"POST",signal:state.abort.signal,
            headers:{"Accept":"application/json","X-CSRFToken":state.favoriteForm.elements.csrfmiddlewaretoken.value},
            body:new URLSearchParams({favorite:state.favorites.has(code) ? "0" : "1"})});
        if (!response.ok) throw new Error("Favorite could not be saved");
        const result = await response.json();
        if (state.abort.signal.aborted) return;
        if (result.country !== code) throw new Error("Incorrect favorite response");
        if (result.favorite) state.favorites.add(code); else state.favorites.delete(code);
        document.dispatchEvent(new CustomEvent("world-journal:data-changed",{detail:{path:url}}));
    } catch (error) {
        if (error.name !== "AbortError") {
            notify({id:"favorite-error",kind:"error",title:"Favorite could not be saved",message:"Try again when the server is available."});
            if (alive(state) && state.code === code) state.page.querySelector("[data-directory-favorite-status]").textContent = "Could not save the favorite. Try again.";
        }
    } finally {
        state.favoritePending.delete(code);
        if (!state.abort.signal.aborted) { favoriteControl(state); renderLists(state); }
    }
}

function initialize() {
    const page = document.querySelector("[data-country-directory]");
    if (!page) return;
    if (controller?.page === page) {
        controller.suspended = false;
        loadContent(controller);
        refreshFavorites(controller);
        return;
    }
    if (controller) { cancelLoad(controller); controller.abort.abort(); }
    const catalog = JSON.parse(page.querySelector("#country-directory-catalog").textContent);
    const state = controller = {page,catalog,byCode:new Map(catalog.map(row => [row.iso_a2,row])),
        form:page.querySelector("[data-directory-filters]"),favoriteForm:page.querySelector("[data-directory-favorite-form]"),
        content:page.querySelector("[data-directory-content]"),code:page.dataset.selectedCountry,tab:page.dataset.selectedTab,
        favorites:new Set(catalog.filter(row => row.favorite).map(row => row.iso_a2)),favoritePending:new Set(),
        cache:new Map(),rows:new Map(),abort:new AbortController(),contentAbort:null,requestId:0,favoriteLoadId:0,timer:null,suspended:false};
    if (state.code) {
        const markup = state.content.innerHTML;
        state.renderedKey = `${state.code}:${state.tab}`;
        state.renderedMarkup = markup;
        if (["articles","videos"].includes(state.tab)) rememberCountryFeed(state.code,state.tab,markup,{notify:false});
        else state.cache.set(`${state.code}:${state.tab}`,{markup});
    }
    page.querySelector("[data-directory-apply]").hidden = true;
    const signal = state.abort.signal;
    // Boosted links must use the newly selected country's current URL.
    page.addEventListener("htmx:configRequest",event => {
        const link = event.detail.elt?.closest("[data-directory-name],[data-directory-map-link]");
        if (link && event.detail.verb === "get") event.detail.path = link.getAttribute("href");
    },{signal});
    state.form.addEventListener("submit",event => {event.preventDefault(); renderLists(state); rememberLocation(state,true);},{signal});
    state.form.addEventListener("input",event => {if (event.target.name === "q") {renderLists(state); rememberLocation(state,true);}},{signal});
    state.form.addEventListener("change",() => {renderLists(state); if (!state.restoringHistory) rememberLocation(state,true);},{signal});
    state.favoriteForm.addEventListener("submit",event => {event.preventDefault(); toggleFavorite(state);},{signal});
    page.addEventListener("click",event => {
        const row = event.target.closest("[data-directory-country]");
        const tab = event.target.closest("[data-directory-tab]");
        if ((row || tab) && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && event.button === 0) {
            event.preventDefault(); select(state,row?.dataset.directoryCountry || state.code,tab?.dataset.directoryTab || state.tab);
            if (row) page.querySelector("[data-directory-detail]").scrollIntoView({block:"start",behavior:"instant"});
        }
        const filter = event.target.closest("[data-news-filter]");
        if (filter) applyArticleFilter(state,filter.dataset.newsFilter);
        if (event.target.closest("[data-directory-retry],[data-news-retry],[data-video-retry]")) loadContent(state,true);
        const play = event.target.closest("[data-video-play]");
        if (play) {
            const bookmark = play.closest(".country-video-item")?.querySelector("[data-bookmark-url]");
            document.dispatchEvent(new CustomEvent("world-journal:play-video",{detail:{videoId:play.dataset.videoId,title:play.dataset.videoTitle,channel:play.dataset.videoChannel,saveUrl:bookmark?.dataset.bookmarkUrl || bookmark?.href}}));
        }
    },{signal});
    page.addEventListener("error",event => {
        if (!event.target.matches("img")) return;
        const fallback = event.target.parentElement.querySelector("[data-flag-fallback]");
        if (fallback) {event.target.hidden = true; fallback.hidden = false;}
        else if (event.target.matches("[data-video-thumbnail]")) event.target.hidden = true;
    },{capture:true,signal});
    window.addEventListener("popstate",() => {
        if (!alive(state) || location.pathname !== "/countries/") return;
        const params = new URL(location.href).searchParams;
        state.restoringHistory = true;
        state.form.elements.q.value = params.get("q") || "";
        state.form.elements.sort.value = ["population","area"].includes(params.get("sort")) ? params.get("sort") : "name";
        state.form.elements.order.value = params.get("order") === "desc" ? "desc" : "asc";
        for (const name of ["sort","order"]) state.form.elements[name].dispatchEvent(new Event("change"));
        select(state,(params.get("country") || "").toUpperCase(),params.get("tab") || "overview",{historyChange:false});
        state.restoringHistory = false;
        document.dispatchEvent(new CustomEvent("world-journal:location-change"));
    },{signal});
    document.addEventListener("world-journal:feed-cache-changed",event => {
        if (alive(state) && event.detail.code === state.code && event.detail.kind === state.tab) renderContent(state,event.detail.entry);
    },{signal});
    document.addEventListener("world-journal:data-changed",event => {
        const path = event.detail?.path || "";
        if (path.startsWith("/journal/") || path.startsWith("/countries/") || path.startsWith("/settings/backups/")) {
            for (const key of state.cache.keys()) if (key.endsWith(":notes")) state.cache.delete(key);
            if (alive(state) && state.tab === "notes") loadContent(state);
        }
        if (path.endsWith("/favorite/") || path.startsWith("/settings/backups/")) refreshFavorites(state);
    },{signal});
    select(state,state.code,state.tab,{historyChange:false});
    refreshFavorites(state);
}

export function registerCountriesPage() {
    if (registered) return;
    registered = true;
    document.addEventListener("world-journal:page-ready",initialize);
    document.addEventListener("world-journal:page-cleanup",event => {
        if (!controller || controller.suspended) return;
        cancelLoad(controller);
        if (event.detail?.preserveCountries) controller.suspended = true;
        else {controller.abort.abort(); controller = null;}
    });
}
