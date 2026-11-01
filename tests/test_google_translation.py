
import os
import requests

api_key = os.getenv("GOOGLE_TRANSLATE_API_KEY")

if not api_key:
    raise RuntimeError("Google Translation API key is missing.")

url = "https://translation.googleapis.com/language/translate/v2"

payload = {
    "q": "Hello, how can I help you?",
    "source": "en",
    "target": "fr",
    "format": "text",
}

response = requests.post(
    url,
    headers={"x-goog-api-key": api_key},
    json=payload,
    timeout=30,
)

print("HTTP status:", response.status_code)
response.raise_for_status()

data = response.json()
translation = data["data"]["translations"][0]["translatedText"]

print("Original: Hello, how can I help you?")
print("French:", translation)
