"""The rules file is the single source of truth for amounts, so it must always parse and stay consistent."""

from datetime import date

import pytest
import yaml
from pydantic import ValidationError

from expat.tools.rules import DEFAULT_RULES_PATH, Rules, load_rules


def _raw_rules() -> dict:
    return yaml.safe_load(DEFAULT_RULES_PATH.read_text(encoding="utf-8"))


def test_rules_file_loads_with_expected_values() -> None:
    rules = load_rules()
    assert rules.version
    assert rules.kindergeld.amount_per_child_eur == 259
    assert rules.elterngeld.basis_min_eur == 300
    assert rules.elterngeld.basis_max_eur == 1800
    assert rules.elterngeld.income_cap_taxable_eur == 175_000
    assert rules.blue_card.min_salary_standard_eur == 50_700
    assert rules.blue_card.min_salary_shortage_eur == pytest.approx(45_934.20)
    assert rules.tenancy_munich.kappungsgrenze_pct == 15
    assert rules.tenancy_munich.valid_until == date(2029, 12, 31)
    assert rules.rundfunkbeitrag.monthly_eur == pytest.approx(18.36)
    assert rules.deadlines["anmeldung"].amount == 14
    assert rules.deadlines["kindergeld_retroactive"].amount == 6
    assert rules.deadlines["elterngeld_retroactive"].amount == 3


def test_every_rule_is_citable_and_verified() -> None:
    rules = load_rules()
    metas = [
        rules.tenancy_notice,
        rules.tenancy_munich,
        rules.kindergeld,
        rules.elterngeld,
        rules.blue_card,
        rules.rundfunkbeitrag,
        rules.schengen,
        *rules.deadlines.values(),
    ]
    for meta in metas:
        assert meta.legal_basis
        assert meta.source_url.startswith("https://")
        assert meta.last_verified >= date(2026, 11, 17)  # all checked in the 2026-11 review


def test_pending_changes_are_listed_by_topic() -> None:
    rules = load_rules()
    ids = {p.id for p in rules.pending_changes}
    assert {"elterngeld_reform_2027", "rundfunkbeitrag_2027", "mietrechtsreform", "steuerklassen_iii_v"} <= ids
    assert rules.pending("elterngeld")[0].affects_from == date(2027, 11, 1)


def test_validity_window_is_inclusive() -> None:
    blue_card = load_rules().blue_card
    assert blue_card.covers(date(2026, 1, 1))
    assert blue_card.covers(date(2026, 12, 31))
    assert not blue_card.covers(date(2027, 1, 1))
    assert not blue_card.covers(date(2025, 12, 31))


def test_misspelt_key_fails_loudly() -> None:
    raw = _raw_rules()
    raw["kindergeld"]["amount_per_chlid_eur"] = raw["kindergeld"].pop("amount_per_child_eur")
    with pytest.raises(ValidationError):
        Rules.model_validate(raw)


def test_unsorted_landlord_tiers_are_rejected() -> None:
    raw = _raw_rules()
    raw["tenancy_notice"]["landlord_months"].reverse()
    with pytest.raises(ValidationError):
        Rules.model_validate(raw)


def test_loader_is_cached() -> None:
    assert load_rules() is load_rules()
