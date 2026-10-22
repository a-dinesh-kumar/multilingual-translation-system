from app.term_protection import postprocess, protect_terms, restore_terms


def test_error_code_and_url_are_restored():
    original = "Visit https://help.example.com and report ERR-500."
    masked, mapping = protect_terms(original)
    assert "https://help.example.com" not in masked
    assert "ERR-500" not in masked
    restored = restore_terms(masked, mapping)
    assert restored == original


def test_product_identifier_is_restored():
    original = "Order AB12345 is delayed."
    masked, mapping = protect_terms(original)
    assert restore_terms(masked, mapping) == original


def test_postprocess_collapses_whitespace():
    assert postprocess("  hello\n   world  ") == "hello world"
