import logging
import google.generativeai as genai
import os
import asyncio
from datetime import datetime, timedelta
from pyrogram import Client, filters
import requests
from keep_alive import keep_alive
from chat_logger import ChatLogger
from datetime import datetime
from googletrans import Translator

# Load your API keys securely from environment variables
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))  # Admin user ID
LOG_CHANNEL_ID = os.environ.get('LOG_CHANNEL_ID')  # Channel ID for logging
ALLOWED_USERS = set(int(id) for id in os.environ.get('ALLOWED_USERS', '').split(',') if id)
ASSISTANT_ACTIVE = True  # Global variable to control assistant state
GF_MODE = {}  # Dictionary to store GF mode state per user

# Initialize database
from replit import db

if not all([TELEGRAM_TOKEN, GEMINI_API_KEY, ADMIN_ID]):
    raise ValueError("Please set all required environment variables: TELEGRAM_TOKEN, GEMINI_API_KEY, and ADMIN_ID")

genai.configure(api_key=GEMINI_API_KEY)

generation_config = {
    "temperature": 0.9,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}

safety_settings = [
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_NONE",
    },
]

# Enable logging
logging.basicConfig(level=logging.INFO)

# Initialize Pyrogram bot client
API_ID = os.environ.get('API_ID')
API_HASH = os.environ.get('API_HASH')

if not API_ID or not API_HASH:
    raise ValueError("Please set API_ID and API_HASH environment variables")

# Initialize chat logger
chat_logger = ChatLogger()

app = Client(
    "telegram-ai-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=TELEGRAM_TOKEN
)

# Assistant control commands
@app.on_message(filters.command(["on", "sa"]) & filters.private)
async def start_assistant(client, message):
    global ASSISTANT_ACTIVE
    chat_id = message.chat.id
    ASSISTANT_ACTIVE = True
    await message.reply("🟢 **Gemini responses are now enabled!**", parse_mode="html")

@app.on_message(filters.command(["off", "ss"]) & filters.private)
async def stop_assistant(client, message):
    global ASSISTANT_ACTIVE
    chat_id = message.chat.id
    ASSISTANT_ACTIVE = False
    await message.reply("🔴 **Gemini responses are now disabled. You can still use commands like /sum!**", parse_mode="html")

# Get Gemini response for text
def get_gemini_response(prompt: str) -> str:
    try:
        model = genai.GenerativeModel(model_name='gemini-2.0-flash',
                                    generation_config=generation_config,
                                    safety_settings=safety_settings)
        response = model.generate_content(prompt)
        return response.text if response.text else "I couldn't generate a response for that."
    except Exception as e:
        return f"Error: {str(e)}"

# Get Gemini response for images
async def get_gemini_vision_response(image_path: str, prompt: str = "") -> str:
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        with open(image_path, 'rb') as img_file:
            image_data = img_file.read()

        default_prompt = """
        Hi! I'm Pahanmi, let me analyze this image for you:
        1. If it's a math problem:
           - I'll explain the type of problem
           - Break it down into simple steps
           - Guide you through the solution
           - Show you the final answer

        2. For any other image:
           - I'll describe what I see
           - Point out interesting details
           - Explain everything clearly

        I'll keep everything simple and easy to understand!
        """

        response = model.generate_content([
            prompt or default_prompt,
            {"mime_type": "image/jpeg", "data": image_data}
        ])

        formatted_response = (
            "🔍 Analysis:\n\n" + 
            response.text.replace("Step ", "\n📝 Step ").replace(". ", ".\n")
        )

        return formatted_response, None
    except Exception as e:
        return f"Error analyzing image: {str(e)}", None

# Handle logs command
@app.on_message(filters.command("logs") & filters.private)
async def view_logs(client, message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("You are not authorized to view logs.")
        return

    try:
        args = message.text.split()
        if len(args) > 1:
            date = datetime.strptime(args[1], "%Y-%m-%d").strftime("%Y-%m-%d")
        else:
            date = datetime.now().strftime("%Y-%m-%d")

        log_file = os.path.join("chat_logs", f"chat_log_{date}.txt")

        if not os.path.exists(log_file):
            await message.reply(f"No logs found for date {date}")
            return

        with open(log_file, "r", encoding="utf-8") as f:
            logs = f.read()

        max_length = 4000
        if len(logs) > max_length:
            chunks = [logs[i:i + max_length] for i in range(0, len(logs), max_length)]
            for chunk in chunks:
                await message.reply(chunk)
        else:
            await message.reply(logs or "No messages found.")

    except Exception as e:
        await message.reply(f"Error reading logs. Usage: /logs YYYY-MM-DD\nExample: /logs 2024-05-23")

# Handle backup command
@app.on_message(filters.command("backup") & filters.private)
async def backup_chats(client, message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("You are not authorized to use the backup command.")
        return

    try:
        time_range = message.text.replace("/backup", "").strip()
        start_str, end_str = [t.strip() for t in time_range.split("-")]

        start_time = datetime.strptime(start_str, "%I:%M%p").replace(
            year=datetime.now().year,
            month=datetime.now().month,
            day=datetime.now().day
        )
        end_time = datetime.strptime(end_str, "%I:%M%p").replace(
            year=datetime.now().year,
            month=datetime.now().month,
            day=datetime.now().day
        )

        chat_history = chat_logger.get_chat_history(start_time, end_time)

        backup_text = "📑 Chat Backup Report\n\n"
        for entry in chat_history:
            backup_text += f"{entry}\n"

        await message.reply(backup_text or "No chat history found for the specified time range.")

    except Exception as e:
        logging.error(f"Error creating backup: {str(e)}")
        await message.reply("Please use the format: /backup 1:00pm - 2:00pm")

# Handle YouTube summarization command
@app.on_message(filters.command("sum") & filters.private)
async def summarize_youtube(client, message):
    try:
        args = message.text.split()
        if len(args) != 2:
            await message.reply("Please provide a YouTube URL.\nFormat: /sum youtube_url")
            return

        url = args[1]
        if "youtube.com" not in url and "youtu.be" not in url:
            await message.reply("Please provide a valid YouTube URL")
            return

        if "youtu.be" in url:
            video_id = url.split("/")[-1]
        else:
            video_id = url.split("v=")[-1].split("&")[0]

        from youtube_transcript_api import YouTubeTranscriptApi

        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        transcript_text = " ".join([t['text'] for t in transcript_list])

        prompt = f"""Please provide a concise summary of this YouTube video transcript. Format the response with:
        - Key points in bullet points
        - Important quotes or highlights
        - Main takeaways
        \n\n{transcript_text}"""
        summary = get_gemini_response(prompt)

        formatted_response = (
            "🎥 *Hello from Pahanmi!* 🎬\n\n"
            f"📌 *Here's what I found in this video*:\n{summary}\n\n"
            "💫 *Hope this helps!* ✨"
        )

        await message.reply(formatted_response, parse_mode="Markdown")

    except Exception as e:
        await message.reply(f"Error summarizing video: {str(e)}\nMake sure the video has English subtitles available.")

# Handle promotion command
@app.on_message(filters.command("promote") & filters.private)
async def promote_user(client, message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("You are not authorized to promote users.")
        return

    try:
        user_id = int(message.text.split()[1])
        ALLOWED_USERS.add(user_id)
        await message.reply(f"User {user_id} has been granted access to the bot.")
    except (IndexError, ValueError):
        await message.reply("Please provide a valid user ID.\nFormat: /promote user_id")

# Handle GF mode command
@app.on_message(filters.command("gfmode") & filters.private)
async def gf_mode_command(client, message):
    try:
        command = message.text.split()[1].lower()
        user_id = str(message.from_user.id)

        if command == "on":
            GF_MODE[user_id] = True
            db[f"gf_mode_{user_id}"] = True
            await message.reply("💝 Girlfriend mode activated! I'll be more romantic and caring now~ 💕")
        elif command == "off":
            GF_MODE[user_id] = False
            db[f"gf_mode_{user_id}"] = False
            await message.reply("Girlfriend mode deactivated. Back to normal mode!")
        else:
            await message.reply("Please use /gfmode on or /gfmode off")
    except Exception as e:
        await message.reply("Please use /gfmode on or /gfmode off")

# Handle start command
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    try:
        user_id = str(message.from_user.id)
        user_info = {
            "name": message.from_user.first_name,
            "username": message.from_user.username,
            "joined_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        db[f"user_{user_id}"] = user_info

        GF_MODE[user_id] = db.get(f"gf_mode_{user_id}", False)

        welcome_text = (
            f"🌸 **Ayubowan {user_info['name']}!** 🌺\n\n"
            "I'm Pahanmi, your Sinhalese friend who speaks English perfectly!\n\n"
            "I can help you with:\n"
            "📸 **Image Analysis** - Send me any image!\n"
            "🎥 **YouTube Summaries** - Use /sum with a link\n"
            "💝 **Girlfriend Mode** - Use /gfmode\n"
            "🌍 **Translation** - Use /translate with text\n\n"
            "Feel free to chat with me in English! 🌟"
        )

        await message.reply(
            welcome_text,
            parse_mode="md"
        )
    except Exception as e:
        logging.error(f"Error in start command: {str(e)}")
        await message.reply("👋 Welcome! I'm your AI Assistant Bot ready to help!")

# Handle messages
@app.on_message(filters.private & (filters.text | filters.photo))
async def handle_message(client, message):
    if message.text and message.text.startswith('/'):
        return

    try:
        if not ASSISTANT_ACTIVE:
            return
        if message.photo:
            logging.info("Received image message")
            photo = message.photo.file_id

            os.makedirs("downloads", exist_ok=True)
            download_path = f"downloads/temp_{message.id}.jpg"

            await message.download(download_path)
            caption = message.caption if message.caption else ""
            reply_text, visualization = await get_gemini_vision_response(download_path, caption)

            await message.reply(reply_text)

            if visualization:
                viz_path = f"downloads/viz_{message.id}.png"
                with open(viz_path, 'wb') as f:
                    f.write(visualization)
                await message.reply_photo(viz_path)
                os.remove(viz_path)

            if os.path.exists(download_path):
                os.remove(download_path)

            # Log to file
            chat_logger.save_message(message.from_user.id, "Image Message")
            chat_logger.save_message(message.from_user.id, reply_text, is_bot_response=True)
            
            # Log to channel
            if LOG_CHANNEL_ID:
                log_text = f"👤 User {message.from_user.id}\n📸 Sent an image"
                if caption:
                    log_text += f"\n💬 Caption: {caption}"
                await client.send_photo(LOG_CHANNEL_ID, photo, caption=log_text)
                await client.send_message(LOG_CHANNEL_ID, f"🤖 Bot response:\n{reply_text}")
        else:
            logging.info(f"Received text message: {message.text}")
            user_id = str(message.from_user.id)
            user_info = db.get(f"user_{user_id}", {})
            user_name = user_info.get("name", "dear")

            if GF_MODE.get(user_id, False):
                prompt = f"""Act as a caring and loving girlfriend responding to: '{message.text}'
                Use cute emojis and be romantic but respectful.
                Call them by their name: {user_name}
                Keep the response short and sweet."""
            else:
                prompt = message.text

            reply_text = get_gemini_response(prompt)
            logging.info(f"Generated response: {reply_text}")

            chat_logger.save_message(message.from_user.id, message.text)
            chat_logger.save_message(message.from_user.id, reply_text, is_bot_response=True)

            # Log to channel
            if LOG_CHANNEL_ID:
                await client.send_message(
                    LOG_CHANNEL_ID,
                    f"👤 User {message.from_user.id}\n💬 Message: {message.text}\n\n🤖 Bot response:\n{reply_text}"
                )

            await message.reply(reply_text)

    except Exception as e:
        logging.error(f"Error handling message: {str(e)}")
        await message.reply("Sorry, I encountered an error processing your message.")

# Daily news report function
async def send_daily_news():
    while True:
        now = datetime.now()
        scheduled_time = now.replace(hour=21, minute=0, second=0, microsecond=0)

        if now >= scheduled_time:
            scheduled_time += timedelta(days=1)

        wait_seconds = (scheduled_time - now).total_seconds()
        await asyncio.sleep(wait_seconds)

        try:
            prompt = """Generate a comprehensive daily news report covering:
            1. Latest technological inventions and innovations
            2. Global football news and match results
            3. Major global conflict updates

            Format with emojis and clear sections. Keep it concise but informative."""

            news_report = get_gemini_response(prompt)
            formatted_report = f"📰 *Daily News Report* 📰\n\n{news_report}\n\n🕘 Generated at {now.strftime('%Y-%m-%d %I:%M %p')}"

            for user_id in ALLOWED_USERS:
                try:
                    await app.send_message(user_id, formatted_report, parse_mode="Markdown")
                except Exception as e:
                    logging.error(f"Failed to send report to user {user_id}: {str(e)}")

        except Exception as e:
            logging.error(f"Error generating daily report: {str(e)}")

# Start the bot
if __name__ == "__main__":
    keep_alive()
    loop = asyncio.get_event_loop()
    loop.create_task(send_daily_news())
    app.run()
