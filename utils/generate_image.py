import openai
import os
from dotenv import load_dotenv
import json
import requests
import io
import base64
from PIL import Image
import concurrent.futures
import asyncio

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
openai.api_base = os.getenv("OPENAI_API_BASE")

MAX_RETRIES = 1
RETRY_DELAY = 0.2  # In seconds

def synchronous_image_create(model, prompt, num_images):
    return openai.Image.create(
        model=model,
        prompt=prompt,
        n=num_images,
        response_format="url"
    )

def synchronous_request_post(url, payload):
    response = requests.post(url, json=payload)
    return response.json()

async def generate_images(prompt, num_images=1):
    loop = asyncio.get_running_loop()

    model_list = ["midjourney", "sdxl", "sdxl", "sdxl", "stable-diffusion-2.1", "kandinsky-2.2", "stable-diffusion-1.5"]
    urls = []
    original_num_images = num_images
    for model in model_list:
        num_images = original_num_images
        retries = 0
        while retries < MAX_RETRIES:
            try:
                if model == "midjourney":
                    num_images = 4
                
                # Make synchronous call in a thread
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    image_response = await loop.run_in_executor(pool, synchronous_image_create, model, prompt, num_images)
                
                for entry in image_response["data"]:
                    urls.append(entry["url"])
                
                print(f"Images generated with model {model}")
                return urls, image_response  # Successfully generated images, so return the URLs
            
            except openai.error.Timeout:
                print(f"Request timed out for model {model}. Retrying... ({retries + 1}/{MAX_RETRIES})")
                retries += 1
                time.sleep(RETRY_DELAY)  # Wait before retrying
                
            except (openai.error.InvalidRequestError, openai.error.PermissionError) as e:
                print(f"An error occurred while using model {model}: {str(e)}")
                break  # If it's not a timeout error, no need to retry, just go to the next model
            
            except openai.error.APIError as e:
                print(f"An error occurred while using model {model}: {str(e)}")
                retries += 1
                time.sleep(RETRY_DELAY)

        if retries == MAX_RETRIES:
            print(f"Failed to generate images with model {model} after {MAX_RETRIES} attempts.")
    
    return None, "Unable to generate images with any model"  # Return an error if no models work

# test generate_images
# async def test_generate_images():
#     prompt = ""
#     urls, image_response = await generate_images(prompt, num_images=2)
#     print(urls)
#     print(image_response)
    
# asyncio.run(test_generate_images())
    
