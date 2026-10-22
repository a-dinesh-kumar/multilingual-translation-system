from app.language_detection import detect_language


def test_clear_english_is_supported():
    result = detect_language("Please cancel my subscription immediately.")
    assert result.iso == "en"
    assert result.supported is True


def test_empty_text_returns_fallback():
    result = detect_language("")
    assert result.iso == "en"
