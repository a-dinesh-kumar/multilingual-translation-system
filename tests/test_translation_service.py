
from app.model_loader import TranslationModel
from app.translation_service import TranslationService


def main():

    print("\n========== GOOGLE TRANSLATION SERVICE TEST ==========\n")

    # Initialize the Google translation client.
    client = TranslationModel()
    client.load()

    service = TranslationService(client)

    # ------------------------------------------------
    # TEST 1: Explicit source language
    # ------------------------------------------------
    print("TEST 1: English -> French")

    result = service.translate(
        text="Hello, how can I help you?",
        source_language="en",
        target_language="fr",
    )

    print("Original:", result.source_text)
    print("Translated:", result.translated_text)
    print("Source:", result.src_iso)
    print("Target:", result.tgt_iso)
    print("Characters:", result.num_input_characters)
    print("Latency:", round(result.latency_ms, 2), "ms")

    # ------------------------------------------------
    # TEST 2: Automatic language detection
    # ------------------------------------------------
    print("\nTEST 2: Automatic language detection")

    result = service.translate(
        text="Bonjour, je voudrais obtenir de l'aide avec ma commande.",
        target_language="en",
    )

    print("Original:", result.source_text)
    print("Detected source:", result.src_iso)
    print("Translated:", result.translated_text)
    print("Detection confidence:", result.detection.confidence)

    # ------------------------------------------------
    # TEST 3: Protected terms
    # ------------------------------------------------
    print("\nTEST 3: Protected terms")

    original_text = (
        "Please visit https://example.com/help "
        "to check your order ORD-12345."
    )

    result = service.translate(
        text=original_text,
        source_language="en",
        target_language="fr",
        protect=True,
    )

    print("Original:", original_text)
    print("Translated:", result.translated_text)

    url_preserved = "https://example.com/help" in result.translated_text
    order_id_preserved = "ORD-12345" in result.translated_text

    print("URL preserved:", url_preserved)
    print("Order ID preserved:", order_id_preserved)

    # ------------------------------------------------
    # TEST 4: Mixed-language batch translation
    # ------------------------------------------------
    print("\nTEST 4: Mixed-language batch translation")

    messages = [
        "Hello, how are you?",
        "Bonjour, comment allez-vous ?",
        "Thank you for contacting customer support.",
        "Merci beaucoup pour votre aide.",
    ]

    results = service.translate_batch(
        messages=messages,
        target_language="en",
    )

    print("\nBatch results:")

    for index, item in enumerate(results):

        print(f"\nMessage {index + 1}")
        print("Original:", item.source_text)
        print("Detected source:", item.src_iso)
        print("Translated:", item.translated_text)

    order_preserved = [
        item.source_text for item in results
    ] == messages

    print("\nOriginal batch order preserved:", order_preserved)

    print("\n========== TESTS COMPLETED ==========")

    client.unload()


if __name__ == "__main__":
    main()
