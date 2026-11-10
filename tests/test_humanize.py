from jobomatic.documents.humanize import find_ai_tells


def test_flags_stock_phrases():
    assert "excited to" in find_ai_tells("I'm excited to apply.")
    assert find_ai_tells("We leveraged a robust pipeline.")


def test_flags_repeated_em_dashes():
    assert find_ai_tells("A \u2014 b \u2014 c")
    assert not find_ai_tells("A \u2014 b")


def test_plain_text_is_clean():
    assert find_ai_tells("I'm applying for the role. I built the API at Acme.") == []
