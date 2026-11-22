import pytest

from expat.places import STATES, SUPPORTED_CITIES, city_label, find_cities, state_for_city


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("How do I register in München?", ["munich"]),
        ("Kita in Köln", ["cologne"]),
        ("Muenchen und Koeln", ["munich", "cologne"]),
        ("moving from Berlin to Munich next month", ["berlin", "munich"]),
        ("Frankfurt am Main Ausländerbehörde", ["frankfurt"]),
        ("Frankfurts Ausländerbehörde", ["frankfurt"]),
        ("I live in Hamburgs suburbs", ["hamburg"]),
        ("Stuttgart-Vaihingen flat", ["stuttgart"]),
        # not Frankfurt am Main / not a city mention
        ("I live in Frankfurt (Oder)", []),
        ("Frankfurt an der Oder", []),
        ("Hamburger Hafen", []),
        ("Berliner Straße 5 in Leipzig", []),
        ("How much Kindergeld do I get?", []),
    ],
)
def test_find_cities(text, expected):
    assert [c.slug for c in find_cities(text)] == expected


def test_supported_cities_have_valid_states():
    assert len(STATES) == 16
    assert all(c.state in STATES for c in SUPPORTED_CITIES.values())
    assert state_for_city("cologne") == "NW" and state_for_city("leipzig") is None
    assert city_label("frankfurt") == "Frankfurt am Main" and city_label("leipzig") == "Leipzig"
