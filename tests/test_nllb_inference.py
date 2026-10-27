
import torch
import transformers
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

MODEL_NAME = "facebook/nllb-200-distilled-600M"

print("PyTorch:", torch.__version__)
print("Transformers:", transformers.__version__)

torch.set_num_threads(1)

print("\n1. Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

print("2. Loading model...")
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
model.eval()

print("3. Checking vocabulary and embeddings...")
print("Tokenizer size:", len(tokenizer))
print("Model vocabulary size:", model.config.vocab_size)
print("Embedding shape:", tuple(model.get_input_embeddings().weight.shape))

print("\n4. Preparing input...")
tokenizer.src_lang = "eng_Latn"
inputs = tokenizer("Hello, how are you?", return_tensors="pt")

print("Input shape:", tuple(inputs["input_ids"].shape))
print("Maximum input token ID:", inputs["input_ids"].max().item())

print("\n5. Testing generation...")
target_id = tokenizer.convert_tokens_to_ids("tam_Taml")

with torch.inference_mode():
    output = model.generate(
        **inputs,
        forced_bos_token_id=target_id,
        max_new_tokens=40,
        num_beams=1,
    )

print("\nTranslation:", tokenizer.batch_decode(
    output, skip_special_tokens=True
)[0])
print("\nNLLB standalone test passed.")
