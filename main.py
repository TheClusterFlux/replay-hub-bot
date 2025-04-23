import discord
import requests
import os
import asyncio
from urllib.parse import urlparse
import json

# Set up intents
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# Replace with your actual API endpoint
# API_URL = "http://localhost:8080/upload"
API_URL = "https://replay-hub.theclusterflux.com"

#test api by calling the metadata endpoint
def test_api():
    try:
        response = requests.get(f"{API_URL}/metadata")
        if response.status_code == 200:
            print("API is reachable.")
        else:
            print(f"API returned status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to API: {e}")
        exit(1)
test_api()

# Whitelist of channel IDs where the bot will respond
# Replace these with your actual channel IDs
WHITELISTED_CHANNELS = [
    1318724534907699210,  # the gaming room clips
    1355169476118708420,  # ragian server general
    # Add more channel IDs as needed
]

# Store ongoing conversations
user_conversations = {}

@client.event
async def on_ready():
    print(f"Logged in as {client.user} and ready to go!")
    print(f"Bot is active in {len(WHITELISTED_CHANNELS)} whitelisted channels")

def is_video_url(url):
    """Check if a URL likely points to a video file"""
    if "cdn.steamusercontent.com" in url:
        return True
    video_extensions = ['.mp4', '.mov', '.avi', '.wmv', '.flv', '.mkv', '.webm']
    parsed = urlparse(url)
    return any(parsed.path.lower().endswith(ext) for ext in video_extensions)

async def collect_info(thread, user):
    """Collect title and description from the user in a thread"""
    # Ask for title
    await thread.send(f"Hi {user.mention}! Please provide a title for this video.\n\nType `cancel` at any time to cancel this submission.")
    
    # Wait for title response
    try:
        def check(m):
            return m.author == user and m.channel == thread
        
        title_msg = await client.wait_for('message', timeout=300.0, check=check)
        
        # Check for cancel
        if title_msg.content.lower() == "cancel":
            await thread.send("Submission canceled.")
            return None, None, True  # Third value indicates cancellation
            
        title = title_msg.content
        
        # Ask for description
        await thread.send("Great! Now please provide a description for the video.\n\nType `cancel` to cancel this submission.")
        desc_msg = await client.wait_for('message', timeout=300.0, check=check)
        
        # Check for cancel
        if desc_msg.content.lower() == "cancel":
            await thread.send("Submission canceled.")
            return None, None, True  # Third value indicates cancellation
            
        description = desc_msg.content
        
        await thread.send("Thanks! Processing your submission...")
        return title, description, False  # Third value indicates no cancellation
    
    except asyncio.TimeoutError:
        await thread.send("You took too long to respond. Please try again by posting a new link.")
        return None, None, False

async def handle_submission(message, url, is_attachment=False):
    """Handle video submission process for both URLs and attachments"""
    # Create a thread for this submission
    thread = await message.create_thread(name=f"Video Upload - {message.author.name}")
    
    # Get additional info from user
    title, description, canceled = await collect_info(thread, message.author)
    
    if not title or not description or canceled:
        await thread.send("This thread will be closed in 2 minutes.")
        # Schedule thread archiving instead of deletion
        await asyncio.sleep(120)
        print("Thread closed due to cancellation or missing info.")
        await thread.edit(archived=True)
        print("Thread closed due to cancellation or missing info.")
        return
    
    # Prepare to send to API
    try:
        # Prepare the request data
        data = {
            "title": title,
            "description": description,
            "s3": "true"  # Store in S3
        }
        
        # Add the file URL to the request
        data["url"] = url
        print(data)
        
        response = requests.post(API_URL+"/upload", data=data)
        
        if response.status_code == 201:
            result = response.json()
            await thread.send(f"✅ Video successfully uploaded!\nTitle: {title}\nDescription: {description}")
            
            # Send additional metadata if available
            if "metadata" in result:
                metadata = result["metadata"]
                metadata_text = f"**Video Details:**\n"
                if "duration" in metadata:
                    metadata_text += f"• Duration: {metadata['duration']} seconds\n"
                if "resolution" in metadata:
                    metadata_text += f"• Resolution: {metadata['resolution']}\n"
                await thread.send(metadata_text)
        else:
            await thread.send(f"❌ Error uploading video: {response.status_code} - {response.text}")
    
    except Exception as e:
        await thread.send(f"❌ Error processing your submission: {str(e)}")
    
    # Notify about thread archiving instead of deletion
    await thread.send("This thread will be closed in 2 minutes.")
    # Schedule thread archiving instead of deletion
    await asyncio.sleep(120)
    await thread.edit(archived=True)

@client.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == client.user:
        return
    
    # Check if the message is in a whitelisted channel
    if message.channel.id not in WHITELISTED_CHANNELS:
        return  # Ignore messages from non-whitelisted channels
    
    
    if message.content == "!help":
        return await message.channel.send(
            "This bot currently only accepts direct video uploads or Steam CDN shares. "
            "Content can be viewed at https://replay-hub.theclusterflux.com. "
            "If you have any questions, please reach out to the admins."
        )
    
    print(f"Received message from {message.author} in whitelisted channel: {message.content}")
    print(f"Attachments: {message.attachments}")
    
    # Check for attachments (videos)
    for attachment in message.attachments:
        if attachment.content_type and attachment.content_type.startswith('video/'):
            # Use the attachment URL directly
            await handle_submission(message, attachment.url, is_attachment=True)
            return
    
    # Check for video URLs in the message content
    words = message.content.split()
    for word in words:
        if word.startswith(('http://', 'https://')) and is_video_url(word):
            await handle_submission(message, word, is_attachment=False)
            return

# Run the bot
if __name__ == "__main__":
    client.run(os.getenv("REPLAY_HUB_DISCORD_TOKEN"))