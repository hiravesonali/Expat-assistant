import pytest

from expat.safety import SafetyCategory, category_for_intent, precheck, safety_response


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("My husband hits me, what can I do?", SafetyCategory.EMERGENCY),
        ("Ich erlebe häusliche Gewalt", SafetyCategory.EMERGENCY),
        ("Can I apply for asylum in Munich?", SafetyCategory.RESIDENCE_RISK),
        ("Droht mir die Abschiebung?", SafetyCategory.RESIDENCE_RISK),
        ("I only have a Duldung, can I work?", SafetyCategory.RESIDENCE_RISK),
        ("Will they deport me if I lose my job?", SafetyCategory.RESIDENCE_RISK),
        ("Mein Vermieter hat eine Räumungsklage eingereicht", SafetyCategory.LEGAL_DISPUTE),
        ("I received an eviction lawsuit", SafetyCategory.LEGAL_DISPUTE),
    ],
)
def test_precheck_flags_sensitive_questions(question, expected):
    assert precheck(question) == expected


@pytest.mark.parametrize(
    "question",
    [
        "My landlord gave me notice, when do I have to move out?",  # eviction-adjacent but in scope
        "How do I register my address in Munich?",
        "Wie viel Kindergeld bekomme ich?",
        "Can my Blue Card family join me?",
    ],
)
def test_precheck_ignores_normal_questions(question):
    assert precheck(question) is None


def test_emergency_template_lists_emergency_numbers_first():
    text = safety_response(SafetyCategory.EMERGENCY, "en")
    assert "110" in text and "112" in text and "116 016" in text
    assert text.index("110") < text.index("bamf-navi")


def test_residence_template_refers_to_mbe_and_lawyer_in_german():
    text = safety_response(SafetyCategory.RESIDENCE_RISK, "de")
    assert "Migrationsberatung für Erwachsene" in text and "anwaltauskunft.de" in text
    assert "keine Rechtsberatung" in text


def test_tenancy_dispute_refers_to_mieterverein():
    assert "mieterverein-muenchen.de" in safety_response(SafetyCategory.LEGAL_DISPUTE)


def test_unknown_language_falls_back_to_english():
    assert safety_response(SafetyCategory.OUT_OF_SCOPE, "other").startswith("Sorry")


def test_intent_mapping():
    assert category_for_intent("sensitive") is SafetyCategory.SENSITIVE
    assert category_for_intent("chitchat") is SafetyCategory.CHITCHAT
    assert category_for_intent("info") is None
