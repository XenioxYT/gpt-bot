import tiktoken

encoding = tiktoken.encoding_for_model("gpt-4")

def count_tokens(text):
    return len(encoding.encode(text))


# from transformers import AutoTokenizer

# # Assuming "llama-model-name" is the identifier for the llama model in Huggingface's model hub.
# # Replace it with the correct model name/ID if it's different.
# tokenizer = AutoTokenizer.from_pretrained("Open-Orca/Mistral-7B-OpenOrca")

# def count_tokens(text):
#     return len(tokenizer.encode(text))

# sample_text = "Hello, world!"
# print(count_tokens(sample_text))
