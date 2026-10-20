"""Pure-function tests for scoring.py: normalisation and the sample-invoice expectations."""

import scoring


def test_corporate_suffix_and_pharma_variant_normalised():
    assert scoring.normalise_name("Northwind Pharmaceuticals Inc.") == "northwind pharma"
    assert scoring.normalise_name("Acme Pharmaceutical Co., Ltd.") == "acme pharma"


def test_name_normalisation_keeps_site_words():
    assert scoring.normalise_name("Prairie Clinical Research") == "prairie clinical research"


def test_person_drops_leading_dr_title():
    assert scoring.normalise_person("Dr. Riley H. Foster") == "riley h foster"


def test_mismatched_sponsor_scores_high():
    assert scoring.name_score("Northwind Pharmaceuticals Inc.", "Northwind Pharma") >= 0.9


def test_exact_sponsor_scores_one():
    assert scoring.name_score("Contoso Therapeutics", "Contoso Therapeutics") == 1.0


def test_wrong_year_protocol_high_but_not_exact():
    s = scoring.protocol_score("NWD-VER-2024-002", "NWD-VER-2023-002")
    assert 0.85 <= s < 1.0


def test_protocol_case_and_separators_ignored():
    assert scoring.protocol_score("nwd ver 2023 002", "NWD-VER-2023-002") == 1.0


def test_wrong_site_name_stays_weak():
    assert scoring.name_score("Prairie Clinical Research", "Prairie Field Research Group") < 0.9


def test_pi_with_middle_initial_matches():
    assert scoring.person_score("Dr. Riley H. Foster", "Dr. Riley Foster") >= 0.9


def test_empty_input_scores_zero():
    assert scoring.name_score("", "Northwind Pharma") == 0.0
    assert scoring.protocol_score("NWD", "") == 0.0


def test_scores_rounded_to_three_places():
    s = scoring.name_score("Prairie Clinical Research", "Willow Creek Clinical Research Center")
    assert s == round(s, 3)


def test_site_rank_without_pi_is_name_score():
    assert scoring.site_rank_score(0.78, None) == 0.78


def test_pi_reorders_but_does_not_change_name_score():
    # ADR-0005: Willow Creek beats Prairie Field on name alone; the PI reorders them.
    willow = scoring.site_rank_score(0.81, 0.24)
    prairie = scoring.site_rank_score(0.78, 1.0)
    assert prairie > willow
