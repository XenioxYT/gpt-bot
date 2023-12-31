import openai
import os
from dotenv import load_dotenv
from google.cloud import vision
from google.oauth2.service_account import Credentials
from transformers import AutoProcessor, Blip2ForConditionalGeneration
import torch
import threading
import requests
from io import BytesIO
from PIL import Image
from flask import Flask, request, jsonify
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import VisualFeatureTypes
from msrest.authentication import CognitiveServicesCredentials
# from utils.exponential_backoff import exponential_backoff

app = Flask(__name__)

# Initialize OpenAI, BLIP and Google Vision API clients
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
openai.api_base = os.getenv("OPENAI_API_BASE")
creds = Credentials.from_service_account_file('creds.json')
client = vision.ImageAnnotatorClient(credentials=creds)

processor = AutoProcessor.from_pretrained("Salesforce/blip2-opt-2.7b")
model = Blip2ForConditionalGeneration.from_pretrained("Salesforce/blip2-opt-2.7b", torch_dtype=torch.float16)
device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)

def google_vision_analysis(image_url):
    # Create an Image instance with the provided URL
    g_image = vision.Image()
    g_image.source.image_uri = image_url

    # Define the features we want
    features = [
        vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION),
        vision.Feature(type_=vision.Feature.Type.FACE_DETECTION),
        vision.Feature(type_=vision.Feature.Type.LABEL_DETECTION),
        vision.Feature(type_=vision.Feature.Type.LANDMARK_DETECTION),
        vision.Feature(type_=vision.Feature.Type.LOGO_DETECTION),
        vision.Feature(type_=vision.Feature.Type.TEXT_DETECTION),
        vision.Feature(type_=vision.Feature.Type.WEB_DETECTION)
    ]

    # Request these features from the Google Vision API
    response = client.annotate_image({'image': g_image, 'features': features})
    
    details = {
        'text': response.full_text_annotation.text,
        'labels': [label.description for label in response.label_annotations],
        'landmarks': [landmark.description for landmark in response.landmark_annotations],
        'logos': [logo.description for logo in response.logo_annotations],
        'faces': len(response.face_annotations),  # number of faces
        'web_entities': [entity.description for entity in response.web_detection.web_entities if entity.score > 0.8],
        # 'web_urls': [page.url for page in response.web_detection.pages_with_matching_images],  # Extracting web URLs
        # 'similar_images_urls': [image.url for image in response.web_detection.visually_similar_images]  # Extracting visually similar images URLs
    }

    return details

from PIL import Image
import requests
from io import BytesIO

def compress_image(img_url, max_size_bytes):
    # Fetch the image
    response = requests.get(img_url)
    image = Image.open(BytesIO(response.content))

    # If the image has an alpha (transparency) channel, convert it to RGB
    if image.mode == "RGBA":
        image = image.convert("RGB")
    
    # Save the image in a buffer using JPEG to compress
    buffer = BytesIO()
    quality = 95
    while True:
        buffer.seek(0)
        image.save(buffer, "JPEG", quality=quality)
        if buffer.tell() <= max_size_bytes or quality <= 10:
            break
        quality -= 5

    buffer.seek(0)
    return buffer


def azure_vision_analysis(image_url):
    key = os.getenv("AZURE_VISION_KEY")
    endpoint = os.getenv("AZURE_VISION_ENDPOINT")
    max_size_bytes = 4 * 1024 * 1024  # 8MB
    
    # Compress the image if it exceeds the max size
    compressed_image = compress_image(image_url, max_size_bytes)

    computervision_client = ComputerVisionClient(endpoint, CognitiveServicesCredentials(key))
    features = [
        VisualFeatureTypes.image_type,
        VisualFeatureTypes.faces,
        VisualFeatureTypes.categories,
        VisualFeatureTypes.color,
        VisualFeatureTypes.tags,
        VisualFeatureTypes.description,
    ]
    
    analysis = computervision_client.analyze_image_in_stream(compressed_image, visual_features=features)

    results = {
        "description": analysis.description.captions[0].text if analysis.description.captions else "",
        "tags": [tag.name for tag in analysis.tags],
        "faces": len(analysis.faces),
        "categories": [category.name for category in analysis.categories],
    }
    
    return results

def blip_caption(image_data, user_message_text):
    # Convert bytes data to PIL Image
    image = Image.open(BytesIO(image_data))
    generated_texts = []

    # 1. Visual Question Answering (VQA) if user message includes '?'
    if "?" in user_message_text:
        prompt = f"Question: {user_message_text} Answer:"
        inputs = processor(image, text=prompt, return_tensors="pt").to(device, torch.float16)
        generated_ids = model.generate(**inputs, max_new_tokens=40)
        generated_texts.append(processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip())

    # 2. Prompted Captioning if user message includes text
    if user_message_text != "No additional text provided.":
        prompt = user_message_text
        inputs = processor(image, text=prompt, return_tensors="pt").to(device, torch.float16)
        generated_ids = model.generate(**inputs, max_new_tokens=40)
        generated_texts.append(processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip())

    # 3. General Captioning without prompt
    inputs = processor(image, return_tensors="pt").to(device, torch.float16)
    generated_ids = model.generate(**inputs, max_new_tokens=40)
    generated_texts.append(processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip())
    
    #4. General Captioning with prompt
    prompt = "In the image there is/are"
    inputs = processor(image, text=prompt, return_tensors="pt").to(device, torch.float16)
    generated_ids = model.generate(**inputs, max_new_tokens=40)
    generated_texts.append(processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip())
    print(generated_texts)
    
    return generated_texts

def get_detailed_caption(image_url, user_message_text):
    # Download the image from the provided URL
    response = requests.get(image_url)
    image_data = BytesIO(response.content).read()

    blip_results = []
    google_result = {}
    azure_result = {}

    def blip_thread():
        nonlocal blip_results
        blip_results = blip_caption(image_data, user_message_text)
    
    def google_thread():
        nonlocal google_result
        google_result = google_vision_analysis(image_url)    

    def azure_thread():
        nonlocal azure_result
        azure_result = azure_vision_analysis(image_url)

    t1 = threading.Thread(target=blip_thread)
    t2 = threading.Thread(target=google_thread)
    t3 = threading.Thread(target=azure_thread)
    
    t1.start()
    t2.start()
    t3.start()
    
    t1.join()
    t2.join()
    t3.join()

    combined_result = {
        "blip": blip_results,
        "google": google_result,
        "azure": azure_result
    }
    
    return combined_result

@app.route('/analyze-image', methods=['POST'])
def analyze_image():
    data = request.json
    image_url = data.get("image_url")
    user_message_text = data.get("message_text", "No additional text provided.")
    if not image_url:
        return jsonify({"error": "Image URL not provided"}), 400
    try:
        analysis = get_detailed_caption(image_url, user_message_text)
        return jsonify(analysis)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(port=6969)

# def example_test():
#     # Sample image URL and message content
#     sample_image_url = "image.com/url"
#     sample_message_content = "Check out this cool image!"

#     caption, web_links = get_detailed_caption(sample_image_url, sample_message_content)
#     print(f"Sample Caption from img2text: {caption}")
#     print(f"Sample Web Links extracted: {web_links}")

# Uncomment the following line to run the example
# example_test()
