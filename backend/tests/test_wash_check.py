from equa_backend.wash_check import find_changed_facts, find_leaked, load_identifiers

IDS = ["Johanna", "Kastanjegatan 14B", "14 mars 1987"]


def test_clean_text_has_no_leaks():
    assert find_leaked("[BORTTAGET] är tech lead sedan 2021.", IDS) == []


def test_leaked_identifier_is_found_ignoring_case():
    assert find_leaked("Kontakta JOHANNA om det.", IDS) == ["Johanna"]


def test_gendered_pronoun_is_a_leak():
    assert find_leaked("Hon ledde teamet.", IDS) == ["pronomen: Hon"]


def test_pronoun_inside_other_word_is_not_a_leak():
    assert find_leaked("Honung och hanterade incidenter.", IDS) == []


def test_contact_details_are_a_leak():
    assert find_leaked("Mejla a@b.se", IDS) == ["kontaktuppgift"]


def test_unchanged_facts_are_not_reported():
    original = "Sänkte kostnaden med 30 procent i PostgreSQL och AWS 2021."
    assert find_changed_facts(original, original, IDS) == []


def test_changed_number_and_term_are_reported():
    original = "Sänkte kostnaden med 30 procent i PostgreSQL."
    washed = "Sänkte kostnaden med 3 procent i databasen."
    assert find_changed_facts(original, washed, IDS) == ["30", "PostgreSQL"]


def test_numbers_inside_identifiers_are_not_facts():
    original = "Född 14 mars 1987. Python i 14 år."
    washed = "Född [BORTTAGET]. Python i 14 år."
    assert find_changed_facts(original, washed, IDS) == []


def test_identifiers_file_skips_comments_and_blank_lines(tmp_path):
    f = tmp_path / "identifierare.txt"
    f.write_text("# kommentar\n\nJohanna\n  Erik  \n", encoding="utf-8")
    assert load_identifiers(f) == ["Johanna", "Erik"]
