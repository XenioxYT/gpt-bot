# Standard library imports
import asyncio
import json
import os
import queue as thread_queue
import random
import sqlite3
import threading
import aiofiles
import concurrent.futures
from openai import OpenAI
import openai

# Related third-party imports
import aiohttp
import discord
from discord import Embed, Bot
from discord.ext import commands, tasks
import openai
from dotenv import load_dotenv
from datetime import datetime
# Local application/library specific imports
from chat_functions import tools
from prompt import initialize_conversation
from strings import typing_indicators, image_analysis_messages, image_generation_messages, google_search_messages, scrape_web_page_messages, status_list
from utils.exponential_backoff import exponential_backoff
from utils.get_conversation import get_conversation
from utils.google_search import google_search
from utils.scrape_web_page import scrape_web_page
from utils.store_conversation import store_conversation
from utils.handle_send_to_discord import update_conversation_and_send_to_discord, send_to_discord, threaded_fetch, generate_response
from utils.image_processing import get_detailed_caption_from_api
from utils.moderate_message import moderate_content
from utils.wolfram_alpha import query_wolfram_alpha
from utils.get_and_set_timezone import set_timezone

from utils.format_message import format_message
# get from environment variables
load_dotenv()
discord_token = os.getenv("DISCORD_TOKEN")
api_key = os.getenv("OPENAI_API_KEY")
api_base = os.getenv("OPENAI_API_BASE")
google_api_key = os.getenv("GOOGLE_API_KEY")
google_cse_id = os.getenv("GOOGLE_CSE_ID")

client = OpenAI(base_url=api_base, api_key=api_key, max_retries=0)

db_conn = sqlite3.connect('conversations.db')
db_conn.execute("""
CREATE TABLE IF NOT EXISTS conversations
    (conversation_id INTEGER PRIMARY KEY,
    conversation TEXT,
    is_busy BOOLEAN)
""")

conversation_locks = {}

# Connect to SQLite database (it will create a new file if not exists)
conn = sqlite3.connect('discord_timezones.db')

# Create a cursor object to execute SQL queries
c = conn.cursor()

# Create new table
c.execute("""
CREATE TABLE IF NOT EXISTS UserTimezones (
    discord_id INTEGER PRIMARY KEY,
    timezone TEXT
);
""")
conn.commit()
conn.close()

async def download_image(url, filename):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                with open(filename, 'wb') as f:
                    f.write(await resp.read())
            else:
                print("Couldn't download the image!")

class ByteClient(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.check_channels_task = None
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    intents.messages = True
    ByteClient = commands.Bot(command_prefix="!", intents=intents)
        
    async def on_ready(self):
        print("Logged on as", self.user)
        self.loop = asyncio.get_running_loop()
        self.change_status_task = self.loop.create_task(self.change_status())
        
    async def change_status(self):
        while not self.is_closed():
            # Change Bot Status
            await self.change_presence(activity=discord.Game(name=random.choice(status_list)))
            await asyncio.sleep(300)  # wait for 5 mins

    async def on_message(self, message):
        if message.author == self.user:
            return
        # Use create_task to run response generation concurrently
        asyncio.create_task(self.respond_to_message(message))
        if not self.check_channels_task or self.check_channels_task.done():
            # Only create the task if it doesn't exist or if the previous task is done
            print("Starting check_channels_for_message task")
            self.check_channels_task = self.loop.create_task(check_channels_for_message(message, self))

    async def respond_to_message(self, message):
        conversation_id = message.channel.id
        is_dm = isinstance(message.channel, discord.DMChannel)
        
        #! Update the last message time
        print("updating last message time")
        update_last_message_time(conversation_id)
        
        def delete_conversation(conversation_id):
            c = db_conn.cursor()
            c.execute("DELETE FROM conversations WHERE conversation_id=?", (conversation_id,))
            db_conn.commit()
            
        async def busy_message(message, text, delay=5):
            msg = await message.reply(text)
            await asyncio.sleep(delay)
            await msg.delete()
            
        if message.content.strip() == '!clear':
            # Check if in a DM
            if is_dm:
                delete_conversation(conversation_id)
                await message.channel.send("Conversation has been cleared.")
                return
            else:
                # Check if the author has the "Bot Manager" role
                if any(role.name == "Bot Manager" for role in message.author.roles):
                    delete_conversation(conversation_id)
                    await message.channel.send("Conversation has been cleared.")
                    return
                else:
                    await message.channel.send("You do not have permission to clear the conversation.")
                    return
                
        if message.content.strip().startswith('!settimezone '):
            new_timezone = message.content.strip()[13:].strip()  # Remove the command prefix and extra spaces

            # Get the Discord ID from the message author
            discord_id = message.author.id  # Replace this line with how you get the Discord ID

            # Attempt to set the new timezone
            if set_timezone(discord_id, new_timezone):
                await message.channel.send(f"Timezone has been set to {new_timezone}.")
            else:
                await message.channel.send("Invalid timezone. Please use a valid IANA Time Zone like 'UTC' or 'America/New_York'.")
            return

        if message.content.strip().startswith('!prompt '):
            if is_dm:
                # delete the conversation
                delete_conversation(conversation_id)
                # create a new conversation, however passing the custom prompt instead of the default one
                conversation = initialize_conversation(conversation_id, is_dm, message.author.id, message.content.strip()[8:].strip())
                await message.channel.send("Conversation has been reset with the custom prompt: " + message.content.strip()[8:].strip())
                return
            else:
                await message.channel.send("You can only use this command in a DM.")
                return
            
        # if message.content.strip().startswith('!settimeframe '):
        #     min_days, max_days = parse_timeframe_command(message.content.strip())
        #     if any(role.name == "Bot Manager" for role in message.author.roles) or is_dm:
        #         if min_days is not None and max_days is not None and min_days <= max_days:
        #             store_user_timeframe(conversation_id, min_days, max_days)
        #             await message.channel.send(f"Timeframe has been set to {min_days} - {max_days} days.")
        #             return
        #         else:
        #             await message.channel.send("Invalid command. Usage: `!settimeframe <min_days> <max_days>`")
        #             return
        #     else:
        #         await message.channel.send("You do not have permission to set the timeframe.")
        #         return

        conversation = get_conversation(conversation_id)
        if conversation is None:
            conversation = initialize_conversation(conversation_id, is_dm, message.author.id)

        if "byte" not in message.content.lower() and not is_dm:
            try:
                content = moderate_content(message)
            except Exception as e:
                print(f"Error occurred when moderating content.")
                return
        else:
            content = message.content
        
        formatted_message = format_message(message.author.id, message.author.name, content.strip())

        new_message = {"role": "user", "content": formatted_message}
        conversation.append(new_message)
        store_conversation(conversation_id, conversation)

        async def edit_message_text(message, content: str):
            await message.edit(content=content)
            
        image_detected = False # Whether an image was detected
        
        if message.attachments and message.attachments[0].content_type.startswith("image/"):
            if conversation_id not in conversation_locks:
                conversation_locks[conversation_id] = asyncio.Lock()

            lock = conversation_locks[conversation_id]
            # Try to acquire the lock
            if lock.locked():
                await edit_message_text(temp_message, "My mind is elsewhere, I'm busy with another task! Please try again after my previous task is done.")
                return

            async with lock:
                image_detected = True
                image_analysis_message = random.choice(image_analysis_messages)
                temp_message = await message.channel.send(image_analysis_message)
    
                # Capture user's message text
                user_message_text = message.content if message.content else "No additional text provided."
    
                # Use the new function to get detailed caption and extracted text
                image_url = message.attachments[0].url
                caption = await get_detailed_caption_from_api(image_url, user_message_text)
                print(f"Caption from img2text: {caption}")
    
                # Construct the content string with the newly extracted data and user's message
                content = (
                    f"{message.author.name} said '{user_message_text}' and sent an image with the contents: '{caption}'. If the user didn't say anything, describe the image and any deductions you can gain from it to the user. "
                    "When given an image caption from a specific source, refrain from disclosing the source or mentioning it in the response. Instead, smoothly integrate the information into your conversational reply as if it was naturally occluded from your analysis of the image."
                )
                print(content)
    
                conversation.append(
                    {
                        "role": "function",
                        "name": "view_image",
                        "content": content.strip(),
                    }
                )
                store_conversation(conversation_id, conversation)
                final_response = ""
                completion = ""
                try:
                    response = await generate_response(conversation, message, conversation_id, client)
                except Exception as e:
                    print(f"Error occurred: {e}")
                    await temp_message.delete()
                    return
                thread_safe_queue = thread_queue.Queue()
                threading.Thread(target=threaded_fetch, args=(response, thread_safe_queue, completion)).start()
    
                completion, temp_message = await send_to_discord(thread_safe_queue, 50, 2000, 0.3, temp_message, final_response, message)
                conversation.append(
                    {
                        "role": "assistant",
                        "content": completion,
                    }
                )
                store_conversation(conversation_id, conversation)
                await temp_message.edit(content=completion[:2000])
                return

        if (("byte" in message.content.lower() or is_dm) and not image_detected):
            if conversation_id not in conversation_locks:
                conversation_locks[conversation_id] = asyncio.Lock()

            lock = conversation_locks[conversation_id]

            # Try to acquire the lock
            if lock.locked():
                await busy_message(message, "My mind is elsewhere, I'm busy with another task! Please try again after my previous task is done.")
                return
            # if is_bot_busy(conversation_id):
            #     asyncio.create_task(busy_message(message, "My mind is elsewhere, I'm busy with another task! Please try again after my previous task is done."))
            #     return
            # else:
            #     set_bot_busy(conversation_id, True)
            async with lock:
                typing_indicator = random.choice(typing_indicators)
                temp_message = await message.channel.send(typing_indicator)
                if is_dm:
                    print('\033[92m' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + " - Byte was called in a DM by " + message.author.name + '\033[0m')
                else:
                    print('\033[94m' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + " - Byte was called in a server by " + message.author.name + '\033[0m')

                def synchronous_api_call(model, latest_conversation):
                    return client.chat.completions.create(
                        model=model,
                        messages=latest_conversation,
                        tools=tools,
                        stream=True,
                        # premium=True
                    )

                # try:
                loop = asyncio.get_running_loop()

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    api_call = lambda model, latest_conversation: loop.run_in_executor(pool, synchronous_api_call, model, latest_conversation)

                    response = await exponential_backoff(
                        api_call,
                        conversation_id=conversation_id,
                        message=message,
                    )
                # except Exception as e:
                #     await temp_message.delete()
                #     return

                thread_safe_queue = thread_queue.Queue()
                final_response = ""
                function_name = None
                function_arguments = ''
                assistant_responses = []
                function_called = False
                # print(response)
                # response_message = response.choices[0].delta
                # print("Response message after selecting:",response_message)
                # tool_calls = response_message.tool_calls
                # if tool_calls:
                #     print("Tool calls:", tool_calls)
                #     return
                for chunk in response:
                    # print(chunk)
                    # print(chunk.choices[0].delta.content)
                    # check if response is regular response
                    if chunk.choices[0].delta.content or chunk.choices[0].delta.content == '':
                        thread_safe_queue.put(chunk.choices[0].delta.content)
                        threading.Thread(target=threaded_fetch, args=(response, thread_safe_queue, final_response)).start()
                        completion, temp_message = await send_to_discord(thread_safe_queue, 75, 2000, 0.3, temp_message, final_response, message)
                        # Instead of appending directly, add to the assistant_responses list
                        # print(completion)
                        assistant_responses.append({
                            "role": "assistant",
                            "content": completion,
                        })
                        # completion = re.sub(r'\[([^\]]+)\]\((http[^)]+)\)', r'[\1](<\2>)', completion)
                        # print(completion)
                        try:
                            await temp_message.edit(content=completion)
                        except discord.errors.HTTPException:
                            print("Failed to edit message. Message too long.")
                            if len(completion) > 4000:
                                current_date = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
                                filename = f"response-{conversation_id}-{current_date}.txt"

                                async with aiofiles.open(filename, 'w') as file:
                                    await file.write(completion)
                                with open(filename, 'rb') as file:
                                    await message.channel.send(file=discord.File(file, filename=filename))
                                    print("Sent response to user as a file.")
                                    os.remove(filename)
                        # print("Final reponse:" + repr(temp_message.content))
                    # check if response is function call
                    try:
                        if chunk.finish_reason == "tool_calls":
                            if "name" in chunk["choices"][0]["delta"]["function_call"]:
                                function_name = chunk["choices"][0]["delta"]["function_call"]["name"]
                            chunk = chunk["choices"][0]["delta"]
                            function_arguments_chunk = chunk["tool_call"]["arguments"]
                            function_arguments += function_arguments_chunk
                            print(function_arguments_chunk, end='', flush=True)
                            if function_called == False:
                                await temp_message.edit(content="I'm deciding on which service to access...")
                            function_called = True
                    except Exception as e:
                        error_message = f"```{str(e)}```" # encloses the error message in code block
                        error_response = f"Oops! An error occurred while processing your request. Here's the technical stuff: {error_message}\nIf the problem persists, please contact Xeniox."
                        await temp_message.edit(content=error_response)
                thread_safe_queue.put(None)  # Sentinel value to indicate end of response

                #add the completion response to the whole conversation
                conversation.extend(assistant_responses)

                #store the conversation after the whole loop has been run
                store_conversation(conversation_id, conversation)
                if function_called == False:
                    return

            if (function_name == "google_search"):  #* Google search function response

                # Check if lock for this conversation exists
                if conversation_id not in conversation_locks:
                    conversation_locks[conversation_id] = asyncio.Lock()

                lock = conversation_locks[conversation_id]

                # Try to acquire the lock
                if lock.locked():
                    await edit_message_text(temp_message, "My mind is elsewhere, I'm busy with another task! Please try again after my previous task is done.")
                    return

                async with lock:
                    function_arguments = json.loads(function_arguments)
                    search_term = function_arguments.get("search_term")
                    num_results = function_arguments.get("num_results")
                    temp_message_text = random.choice(google_search_messages).format(search_term)
                    await edit_message_text(temp_message, temp_message_text)
                    function_response = google_search(search_term=search_term, num_results=num_results, api_key=google_api_key, cse_id=google_cse_id,)
                    function_response = "Give these results to the user in a conversational format, not a list. Never deliver the results in a list. Here they are: " + function_response
                    await update_conversation_and_send_to_discord(function_response, function_name, temp_message, conversation, conversation_id, message, client)

            elif (function_name == "scrape_web_page"):  #* Scrape web page function response
                # Check if lock for this conversation exists
                if conversation_id not in conversation_locks:
                    conversation_locks[conversation_id] = asyncio.Lock()

                lock = conversation_locks[conversation_id]

                # Try to acquire the lock
                if lock.locked():
                    await edit_message_text(temp_message, "My mind is elsewhere, I'm busy with another task! Please try again after my previous task is done.")
                    return

                async with lock:
                    function_arguments = json.loads(function_arguments)
                    url = function_arguments.get("url")
                    temp_message_text = random.choice(scrape_web_page_messages).format(url)
                    await edit_message_text(temp_message, temp_message_text)
                    function_response = scrape_web_page(url)
                    await update_conversation_and_send_to_discord(function_response, function_name, temp_message, conversation, conversation_id, message, client)

            elif (function_name == "ask_wolfram_alpha"):  #* Ask Wolfram Alpha function response
                # Check if lock for this conversation exists
                if conversation_id not in conversation_locks:
                    conversation_locks[conversation_id] = asyncio.Lock()

                lock = conversation_locks[conversation_id]

                # Try to acquire the lock
                if lock.locked():
                    await edit_message_text(temp_message, "My mind is elsewhere, I'm busy with another task! Please try again after my previous task is done.")
                    return

                async with lock:
                    function_arguments = json.loads(function_arguments)
                    query = function_arguments.get("query")
                    temp_message_text = "Checking my answer for " + query
                    await edit_message_text(temp_message, temp_message_text)
                    function_response = query_wolfram_alpha(query)
                    await update_conversation_and_send_to_discord(function_response, function_name, temp_message, conversation, conversation_id, message, client)

    @ByteClient.application_command(name="hello", description="Say hello to the bot!")
    async def hello_command(self, ctx: discord.ApplicationContext):
        await ctx.respond(f"Hello {ctx.author.name}!")
    async def setup_hook(self):
        # Register your slash commands here
        self.tree.add_command(self.hello_command)
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.messages = True
DiscordClient = ByteClient(command_prefix="!", intents=intents)
DiscordClient.run(discord_token)
