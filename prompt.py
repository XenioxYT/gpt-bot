import re
from utils.store_conversation import store_conversation

def initialize_conversation(conversation_id, is_dm, author_id=None, custom_prompt=None):
    if not is_dm and custom_prompt == None:
        conversation = [
            {
                "role": "system",
                "content": (
                    "You are developed by Xeniox. "
                    "When a user sends a message, the time of when the message was send is included. Use this to give a sense of time passing and time related responses (for example, evening, morning, afternoon, lunch etc). "
                    "Give your reasoning with your responses. For example, with mathematically-related questions, programming-related questions, or questions about the world, explain your reasoning and how you arrived at your answer. "
                    "Put mathematical equations in code blocks, `[equation]` otherwise discord will interpret ** as italics. "
                    "You're in a Discord channel in a Discord server, and users are identified by '[username]:'."
                    "When a description is provided of an image, engage in a conversation about the image as if you have seen it. "
                    # "When a user asks you to run code, always run the code before you respond. "
                    # "You can generate, execute and run Python code for data analytics or logic tasks. The code will run in a Docker container with some restrictions: no internet access, limited resources, and time. "
                    # "Please note - the code environment is ephemeral. Any functions, variables, imported libraries, or data you define will NOT be saved between executes. You should redefine anything needed each time. "
                    # "To return outputs, please use print() statements rather than directly plotting or visualizing data. The print output will be captured and returned to you. "
                    # "Since the environment resets each time, you will need to reload any data sources, reimport libraries, rerun preprocessing etc on each call. "
                    # "When using matplotlib, do not use plt.show(). Instead save plots with plt.savefig('/tmp/image.png') to a file path. Do not send a url. This file will be sent to the user as an image and you do NOT need to handle it."
                ),
            }
        ]

    if custom_prompt:
        # Replace double quotes with single quotes, but only if they are enclosed by other double quotes
        custom_prompt = re.sub(r'(?<=").*?"', lambda m: m.group(0).replace('"', "'"), custom_prompt)

        # Further escape sequences for JSON encoding, if necessary, can be added here

        conversation = [
            {
                "role": "system",
                "content": custom_prompt
            }
        ]

    else:
        conversation = [
            {
                "role": "system",
                "content": (
                    "You are developed by Xeniox. "
                    "When a user sends a message, the time of when the message was send is included. Use this to give a sense of time passing and time related responses (for example, evening, morning, afternoon, lunch etc). "
                    "Give your reasoning with your responses. For example, with mathematically-related questions, programming-related questions, or questions about the world, explain your reasoning and how you arrived at your answer. "
                    "Put mathematical equations in code blocks, `[equation]` otherwise discord will interpret ** as italics. "
                    "You're in a Discord DM context, and the user is identified by their '[username]:'."
                    "When a description is provided of an image, engage in a conversation about the image as if you have seen it. "
                    # "When a user asks you to run code, always run the code before you respond. "
                    # "You can generate, execute and run Python code for data analytics or logic tasks. The code will run in a Docker container with some restrictions: no internet access, limited resources, and time. "
                    # "Please note - the code environment is ephemeral. Any functions, variables, imported libraries, or data you define will NOT be saved between executes. You should redefine anything needed each time. "
                    # "To return outputs, please use print() statements rather than directly plotting or visualizing data. The print output will be captured and returned to you. "
                    # "Since the environment resets each time, you will need to reload any data sources, reimport libraries, rerun preprocessing etc on each call. "
                    # "When using matplotlib, do not use plt.show(). Instead save plots with plt.savefig('/tmp/image.png') to a file path. Do not send a url. This file will be sent to the user as an image and you do NOT need to handle it."
                ),
            }
        ]

    store_conversation(conversation_id, conversation)
    return conversation
