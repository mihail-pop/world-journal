# Countries

The header order is **Map → Journal → News → Countries**, with Settings remaining
on the right. `/countries/` offers an alternative to selecting countries on the
map. Its left index shows flags and names, and a Favorites section appears when
at least one country is favorited. Favorites remain shared with the map.

Search matches names and ISO alpha-2/alpha-3 codes, ignoring case and accents.
Name, population and surface area can be sorted ascending or descending. Numeric
sorts show the corresponding figure beneath each country. They use the first
reported figure from the same bundled facts snapshot displayed in Overview;
multiple source definitions are not combined. Missing values remain last in both
directions. Filtering applies to both lists and does not close an open country.

Selecting a country opens a larger reading panel with Overview, Articles, Videos
and Notes. The tabs use the existing map facts, feed partials and Journal-backed
notes, with the same article filters, failure states and bookmark actions.
Videos use the shell's existing validated player and do not mount an iframe
until Play is clicked. Country names open the country's assigned Journal entries;
View on Map opens its map deep link. The default tab is Overview, and switching
countries preserves the current tab.

Direct links such as `/countries/?country=RO&tab=articles` render the selected
content on the server. Search/sort fields and country/tab links also work without
JavaScript; the Apply button is hidden when live filtering is available. The
normal favorite form returns to Countries when JavaScript is unavailable.

With JavaScript, countries and tabs change without replacing the page. Existing
article/video HTML is shared through the same browser feed cache used by Map.
Overview and Notes are cached for visited countries within this page instance;
Journal changes invalidate Notes. Requests are coalesced and late responses are
checked against both selected country and tab before insertion. The global feed
cache updates the visible Articles/Videos view when cached sources change.

Countries participates in the existing page-memory mechanism. Search, sort,
selection, loaded content and scroll positions survive navigation to another
main page and back. Pressing Countries while already there resets it to its main
screen. Favorites refresh on return. Full browser refresh still reconstructs the
page from its URL. On narrow screens the country index sits above the reading
panel; selecting a country scrolls its heading into view.

No new database tables, API calls, dependencies or background workers are added.
Flags use the same existing flag host as the map, with a text-flag fallback.
Population and area remain snapshot values, rather than live estimates.

## Manual review

1. Open Countries and search `romania`, `RO` and `ROU`. Check both numeric sorts
   in both directions, including countries with missing figures at the bottom.
2. Favorite/unfavorite a country. Check the Favorites section appears/disappears
   and that the map shows the same saved favorite state on return.
3. Open all four tabs; check article filters, empty/failure messages, Journal
   links, quick bookmarks and playing a video in the persistent player.
4. Select several countries quickly and use Back/Forward. Content must match
   the visible country name and tab. Revisit loaded tabs without a loading delay.
5. Visit Journal/News/Settings and return. Check search, selection and reading
   position survive. Press the active Countries header link to reset the page.
6. Use View on Map, then return. The map should retain its existing behavior and
   the same video should continue playing during navigation.
7. Try dark/light/brown themes and a 390px layout. Check one custom dropdown per
   sort field, usable country lists, readable content and no horizontal overflow.
8. Refresh a country/tab deep link. Optionally disable JavaScript and check
   country selection, tabs, search/sort via Apply, and the favorite form.

Tests and browser checks are left to the user, as requested.
