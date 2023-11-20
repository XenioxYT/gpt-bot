from utils.get_and_set_timezone import get_timezone
import datetime
import pytz

def format_message(discord_id, username, content):

    # Use the timezone associated with the user's Discord ID
    user_timezone = get_timezone(discord_id)
    timezone = pytz.timezone(user_timezone)
    
    # Get current time in the specified timezone
    current_time = datetime.datetime.now(timezone)
    
    # Format the date and time
    formatted_time = current_time.strftime("%a %d/%m/%y %H:%M %Z")
    
    # Return the formatted message string
    return f"At {formatted_time} {discord_id} ({username}) said: {content.strip()}"
from utils.get_and_set_timezone import get_timezone
import datetime
import pytz

def format_message(discord_id, username, content):

    # Use the timezone associated with the user's Discord ID
    user_timezone = get_timezone(discord_id)
    timezone = pytz.timezone(user_timezone)
    
    # Get current time in the specified timezone
    current_time = datetime.datetime.now(timezone)
    
    # Format the date and time
    formatted_time = current_time.strftime("%a %d/%m/%y %H:%M %Z")
    
    # Return the formatted message string
    return f"At {formatted_time} {discord_id} ({username}) said: {content.strip()}"