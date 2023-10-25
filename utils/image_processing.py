import aiohttp
import json

async def get_detailed_caption_from_api(image_url, user_message_text):
    API_ENDPOINT = "http://localhost:6969/analyze-image"
    payload = {
        "image_url": image_url,
        "message_text": user_message_text
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(API_ENDPOINT, json=payload) as response:
            if response.status == 200:
                data = await response.json()

                # Azure
                azure_description = data['azure'].get('description', '')
                azure_tags = ", ".join(data['azure'].get('tags', []))
                azure_categories = ", ".join(data['azure'].get('categories', []))
                azure_faces = data['azure'].get('faces', '')


                # Blip
                blip_data = ". ".join(data['blip'])

                # Google
                google_labels = ", ".join(data['google']['labels'])
                google_text = data['google']['text']
                google_web_entities = ", ".join(data['google']['web_entities'])

                # Combining
                caption = (f"{azure_description}. Tags: {azure_tags}. Categories: {azure_categories}. "
                           f"Faces detected by Azure: {azure_faces}. {blip_data}. Google Labels: {google_labels}. "
                           f"Text detected by Google: {google_text}. Google Web Entities: {google_web_entities}")

                return caption.strip()
            else:
                print(f"Error {response.status}: {await response.text()}")
                return "Failed to retrieve caption"

