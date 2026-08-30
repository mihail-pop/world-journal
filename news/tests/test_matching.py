from django.test import SimpleTestCase

from news.services.country_matcher import MatchClass, match_country_text, matched_country_codes
from news.services.country_news import _country_for_code
from news.services.region_routing import routing_groups_for_country


class RegionRoutingTests(SimpleTestCase):
    def assert_groups(self, code, expected):
        self.assertEqual(routing_groups_for_country(_country_for_code(code)), frozenset(expected))

    def test_explicit_transcontinental_and_boundary_rules(self):
        self.assert_groups("TR", {"middle_east", "europe"})
        self.assert_groups("RU", {"europe", "asia_pacific"})
        self.assert_groups("EG", {"africa", "middle_east"})
        self.assert_groups("CY", {"middle_east", "europe"})
        self.assert_groups("MX", {"north_america", "latin_america_caribbean"})

    def test_central_america_caribbean_and_oceania(self):
        self.assert_groups("BZ", {"latin_america_caribbean"})
        self.assert_groups("JM", {"latin_america_caribbean"})
        self.assert_groups("AU", {"asia_pacific"})


class CountryTitleMatcherTests(SimpleTestCase):
    def assert_codes(self, title, *codes):
        self.assertEqual(matched_country_codes(title), frozenset(codes))

    def test_complete_words_prevent_oman_romania_and_niger_nigeria_collisions(self):
        self.assert_codes("Romania votes in parliamentary election", "RO")
        self.assert_codes("Omani officials visit Romania", "OM", "RO")
        self.assert_codes("Nigeria announces a new budget", "NG")
        self.assert_codes("Niger and Nigeria reopen their border", "NE", "NG")

    def test_longest_guinea_alias_wins_without_hiding_separate_mentions(self):
        self.assert_codes("Guinea-Bissau election results", "GW")
        self.assert_codes("Equatorial Guinea signs agreement", "GQ")
        self.assert_codes("Papua New Guinea parliament meets", "PG")
        self.assert_codes("Guinea and Guinea-Bissau hold talks", "GN", "GW")

    def test_specific_congo_and_korea_names_do_not_overlap(self):
        self.assert_codes("Democratic Republic of the Congo holds vote", "CD")
        self.assert_codes("Republic of the Congo and DRC sign accord", "CG", "CD")
        self.assert_codes("North Korea responds to South Korean proposal", "KP", "KR")

    def test_ambiguous_person_and_place_names_prefer_omission(self):
        self.assert_codes("Georgia wins college football opener")
        self.assert_codes("Michael Jordan memorabilia sells at auction")
        self.assert_codes("Chad Smith announces a tour")
        self.assert_codes("How to roast a turkey for dinner")
        self.assert_codes("Georgian parliament approves bill", "GE")
        self.assert_codes("Jordanian ministers meet", "JO")
        self.assert_codes("Chadian voters cast ballots", "TD")
        self.assert_codes("Türkiye and Turkish officials respond", "TR")

    def test_canonical_capitals_are_title_only_related_evidence(self):
        matches = match_country_text("Tehran and London hold talks", "Ankara watches closely")

        self.assertEqual(
            [(match.country_code, match.match_class) for match in matches],
            [("GB", MatchClass.HEADLINE_RELATED), ("IR", MatchClass.HEADLINE_RELATED)],
        )

    def test_summary_names_aliases_and_demonyms_are_lower_priority(self):
        matches = match_country_text(
            "Energy markets react",
            "Iran and British officials discussed the Iranian outlook.",
        )

        self.assertEqual({match.country_code for match in matches}, {"IR", "GB"})
        self.assertTrue(all(match.match_class is MatchClass.SUMMARY_COUNTRY for match in matches))

    def test_iran_and_turkey_forms_retain_ambiguity_protection(self):
        self.assert_codes("Iran and Iranian officials meet", "IR")
        self.assert_codes("Turkey dinner tips")
        self.assert_codes("Türkiye and Turkish officials meet", "TR")

    def test_case_sensitive_acronyms_do_not_match_lowercase_pronouns(self):
        self.assert_codes("The decision surprised us")
        for title in ("US officials respond", "U.S. officials respond", "USA officials respond"):
            with self.subTest(title=title):
                self.assert_codes(title, "US")

    def test_reviewed_uk_us_and_renamed_country_aliases(self):
        cases = {
            "United Kingdom and U.K. ministers meet": {"GB"},
            "Britain reviews British policy": {"GB"},
            "United States and American officials meet": {"US"},
            "Côte d’Ivoire and Ivory Coast are alternate names": {"CI"},
            "Czechia updates Czech Republic law": {"CZ"},
            "Eswatini marks anniversary of Swaziland renaming": {"SZ"},
            "Myanmar and Burma appear in the headline": {"MM"},
        }
        for title, codes in cases.items():
            with self.subTest(title=title):
                self.assertEqual(matched_country_codes(title), frozenset(codes))

    def test_multi_country_and_candidate_filtering(self):
        title = "France, Germany and Romania discuss Europe policy"
        self.assert_codes(title, "FR", "DE", "RO")
        self.assertEqual(matched_country_codes(title, {"FR", "RO"}), frozenset({"FR", "RO"}))

    def test_arbitrary_substrings_do_not_match(self):
        self.assert_codes("A romanianapolis typo and omankind slogan")