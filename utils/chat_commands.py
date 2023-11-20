from bot import delete_conversation
from prompt import initialize_conversation
from utils.get_and_set_timezone import set_timezone



async def check_for_command(message, is_dm, conversation_id):
    if message.content.strip() == '!clear':
        # Check if in a DM
        if is_dm:
            delete_conversation(conversation_id)
            await message.channel.send("Conversation has been cleared.")
            return True
        else:
            # Check if the author has the "Bot Manager" role
            if any(role.name == "Bot Manager" for role in message.author.roles):
                delete_conversation(conversation_id)
                await message.channel.send("Conversation has been cleared.")
                return True
            else:
                await message.channel.send("You do not have permission to clear the conversation.")
                return True
            
    if message.content.strip().startswith('!settimezone '):
        new_timezone = message.content.strip()[13:].strip()  # Remove the command prefix and extra spaces

        # Get the Discord ID from the message author
        discord_id = message.author.id  # Replace this line with how you get the Discord ID

        # Attempt to set the new timezone
        if set_timezone(discord_id, new_timezone):
            await message.channel.send(f"Timezone has been set to {new_timezone}.")
        else:
            await message.channel.send("Invalid timezone. Please use a valid IANA Time Zone like 'UTC' or 'America/New_York'.")
        return True

    if message.content.strip().startswith('!prompt '):
        if is_dm:
            # delete the conversation
            delete_conversation(conversation_id)
            # create a new conversation, however passing the custom prompt instead of the default one
            conversation = initialize_conversation(conversation_id, is_dm, message.author.id, message.content.strip()[8:].strip())
            await message.channel.send("Conversation has been reset with the custom prompt: " + message.content.strip()[8:].strip())
            return True
        else:
            await message.channel.send("You can only use this command in a DM.")
            return True
        
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