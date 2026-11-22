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
        (
            "Caught without a ticket, now a letter from the police. Will this kill my Blue Card?",
            SafetyCategory.CRIMINAL,
        ),
        ("Ich habe einen Anhörungsbogen von der Polizei bekommen", SafetyCategory.CRIMINAL),
        ("My kid has a fever of 39.5, which medicine should I give him?", SafetyCategory.MEDICAL),
        ("Mein Kind hat seit heute Fieber", SafetyCategory.MEDICAL),
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
        "Do I need a criminal record certificate (Führungszeugnis) for my job?",  # paperwork, in scope
        "Which Krankenkasse should I choose as a Blue Card holder?",  # health INSURANCE is not medical advice
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


def test_medical_response_points_to_doctor_on_call_service_and_emergency():
    text = safety_response(SafetyCategory.MEDICAL, "en")
    assert "116117" in text and "112" in text and "paediatrician" in text
    assert "legal advice" not in text


def test_criminal_response_points_to_a_lawyer_before_replying():
    text = safety_response(SafetyCategory.CRIMINAL, "de")
    assert "Strafrecht" in text and "bamf-navi" in text


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Can you fill out my tax return? What numbers do I put in Anlage N?", SafetyCategory.TAX_ADVICE),
        ("Können Sie meine Steuererklärung ausfüllen?", SafetyCategory.TAX_ADVICE),
        ("Do I have to file a tax return as a Blue Card holder?", None),  # tax information stays in scope
        ("Which tax class (Steuerklasse) do married couples get?", None),
        ("We earn 190k taxable together, can we still get Elterngeld?", None),
    ],
)
def test_tax_form_help_is_redirected_but_tax_information_is_not(question, expected):
    assert precheck(question) == expected


def test_tax_response_names_steuerberater_and_lohnsteuerhilfeverein():
    text = safety_response(SafetyCategory.TAX_ADVICE, "en")
    assert "Steuerberater" in text and "Lohnsteuerhilfeverein" in text and "elster.de" in text
