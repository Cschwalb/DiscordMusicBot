import asyncio
import collections
import os
import random
import discord
from discord.ext import commands # This import is compatible with py-cord for prefix commands
from dotenv import load_dotenv
import yt_dlp as youtube_dl
from pytube import Playlist

# Ensure this path is correct for your .env file
load_dotenv()
DISCORD_TOKEN=os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    print("Error DISCORD TOKEN NOT FOUND IN .env file or environmental variable")
    exit(1)

# Global deque for the music queue
# Each item in the deque will be a dictionary: {'url': '...', 'title': '...'}
deq = collections.deque()

intents = discord.Intents.default()
intents.message_content = True # Required for reading command arguments
intents.guilds = True # Required for guilds
intents.voice_states = True # Required for voice channel operations



# Using commands.Bot is correct for prefix commands in py-cord as well
bot = commands.Bot(command_prefix='!', intents=intents)
#youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'restrictfilenames': True,
    'noplaylist': True, # We handle playlists separately with pytube, so yt-dlp won't try to download all
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn' # -vn means no video, just audio
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

# --- Helper Functions ---

def analyze_input(analysis):
    # If it's a direct URL, return it
    if "http" in analysis:
        if "&" in analysis:
            st = analysis.split('&')
            return st[0]
        return analysis
    # Otherwise, perform a Youtube
    return search_youtube(analysis)

def search_youtube(keyword) -> str:
    try:
        # Use ytsearch: to search YouTube and get the first result's URL
        info = ytdl.extract_info('ytsearch:' + keyword, download=False)['entries'][0]
        return info['webpage_url']
    except Exception as e:
        print(f"Error during Youtube for '{keyword}': {e}")
        # Return a known URL or handle more gracefully, perhaps raise an exception
        # For now, let's return something that will likely fail to play for feedback
        return 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' # Rick Roll for fun, or better error message

# --- Music Playback Logic ---

async def play_next_song(ctx):
    if len(deq) > 0:
        song_info = deq.popleft() # Get the next song from the queue
        url = song_info['url']
        title = song_info['title']

        server = ctx.message.guild
        voice_client = server.voice_client

        if voice_client and voice_client.is_connected():
            try:
                # Extract the direct stream URL (download=False)
                # This needs to be done right before playing as stream URLs can expire
                data = await bot.loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
                if 'entries' in data: # Handle cases where a playlist link might be passed, take the first entry
                    data = data['entries'][0]

                stream_url = data['url'] # This is the actual direct audio stream URL

                await ctx.send(f"```[+]Now playing[+] {title}```")
                try:
                    # discord.FFmpegPCMAudio is also compatible
                    audio = discord.FFmpegPCMAudio(stream_url, executable="ffmpeg.exe", options="-vn")
                    voice_client.play(audio,
                                      after=lambda e: print(f"Error in playback: {e}") if e else bot.loop.create_task(
                                          play_next_song(ctx)))
                except Exception as e:
                    await ctx.send(f"FFmpeg playback setup failed: {e}")
            except Exception as e:
                await ctx.send(f"Error playing song: '{title}' - {e}")
                print(f"Error playing song: '{title}' - {e}")
                # If there's an error with the current song, try playing the next one
                bot.loop.create_task(play_next_song(ctx))
        else:
            await ctx.send("Bot is not connected to a voice channel. Use `!join` first.")
            deq.clear() # Clear queue if bot isn't in channel
    else:
        await ctx.send("Queue finished! Use `!cleanup` if you have any leftover files (unlikely with streaming).")


# --- Bot Commands ---

@bot.event
async def on_ready():
    try:
        print(f'{bot.user} has connected to Discord!')
        print(f'Bot is ready! Connected to {len(bot.guilds)} guilds.')
        print('[!]------')
    except Exception as e:
        print(f"Error during on_ready event: {e}")

@bot.event
async def on_connect():
    """Called when the client has successfully connected to Discord."""
    print("Bot has successfully connected to Discord Gateway.")

@bot.event
async def on_disconnect():
    """Called when the client has disconnected from Discord, or a connection attempt to Discord has failed."""
    print("Bot has disconnected from Discord Gateway.")
    await bot.close()
    print("Bot has closed")

@bot.command(name='join', help='Tells the bot to join the voice channel')
async def join(ctx):
    # Check if bot is already in a voice channel
    if ctx.voice_client: # ctx.voice_client is a shortcut for ctx.guild.voice_client
        if ctx.guild.voice_client.channel == ctx.author.voice.channel:
            await ctx.send(f"I am already in your voice channel: {ctx.voice_client.channel.name}")
            return
        else:
            # Optionally, disconnect from the old channel before joining a new one
            await ctx.voice_client.disconnect()
            await ctx.send(f"Left {ctx.voice_client.channel.name} to join your channel.")

    if not ctx.message.author.voice:
        await ctx.send(f"{ctx.message.author.name} is not connected to a voice channel.")
        return
    else:
        channel = ctx.message.author.voice.channel
    try:
        print("before connect")
        vc = await channel.connect()
        print("connected!")
    except discord.errors.ConnectionClosed as e:
        if e.code == 4006:
            print("Session timed out. Reconnecting...")
            await asyncio.sleep(2)
            vc = await channel.connect(reconnect=True)
        else:
            print(f"ConnectionClosed error during join: {e}")
            await ctx.send(f"Failed to join voice channel: {e}")
    except discord.ClientException as e: # Catch ClientException for cases like already connected
        await ctx.send(f"I am already trying to join or am in a voice channel: {e}")
        print(f"ClientException during join: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during join: {e}")
        await ctx.send(f"An error occurred while trying to join: {e}")
    await ctx.send(f"Joined voice channel: {channel.name}")

@bot.command(name='leave', help='Tells the bot to leave the voice channel')
async def leave(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        deq.clear() # Clear the queue when leaving
        await ctx.send("Left the voice channel and cleared the queue.")
    else:
        await ctx.send("The bot is not connected to a voice channel.")

@bot.command(name='pn', help='Plays a song or adds it to the queue. Usage: !play <URL or search term>')
async def play(ctx, *, url_or_search_term):
    server = ctx.message.guild
    voice_client = server.voice_client

    if not voice_client.is_connected():
        await ctx.send("I'm not in a voice channel. Use `!join` first.")
        print("not joined from pn...")
        return

    async with ctx.typing():
        try:
            processed_url = analyze_input(url_or_search_term)

            # --- ADD THIS CHECK ---
            if processed_url is None:
                await ctx.send(f"Could not find a video for '{url_or_search_term}'. Please try a different search term or a direct URL.")
                return

            info = await bot.loop.run_in_executor(None, lambda: ytdl.extract_info(processed_url, download=False))
            if 'entries' in info:
                info = info['entries'][0]

            song_info = {'url': info['webpage_url'], 'title': info['title']}

            if voice_client.is_playing() or voice_client.is_paused():
                deq.append(song_info)
                await ctx.send(f"```Added '{song_info['title']}' to the queue. Position: {len(deq)}.```")
            else:
                deq.appendleft(song_info)
                await ctx.send(f"```Playing '{song_info['title']}' now!```")
                await play_next_song(ctx)

        except Exception as e:
            await ctx.send(f"Could not process your request: {e}")
            print(f"Error in !play: {e}")

@bot.command(name='playlist', help='Adds all songs from a YouTube playlist to the queue. Usage: !playlist <URL>')
async def add_playlist(ctx, url):
    server = ctx.message.guild
    voice_client = server.voice_client

    if not voice_client.is_connected():
        await ctx.send("I'm not in a voice channel. Use `!join` first.")
        return

    await ctx.send("```Processing playlist... this may take a moment.```")
    try:
        playlist_obj = Playlist(url)
        if not playlist_obj.video_urls:
            await ctx.send("No videos found in that playlist or invalid URL.")
            return

        added_count = 0
        for video_url in playlist_obj.video_urls:
            try:
                # Extract basic info without downloading
                info = await bot.loop.run_in_executor(None, lambda: ytdl.extract_info(video_url, download=False))
                if 'entries' in info: # This handles YouTube Mixes too
                    info = info['entries'][0]
                song_info = {'url': info['webpage_url'], 'title': info['title']}
                deq.append(song_info)
                added_count += 1
            except Exception as e:
                print(f"Skipping problematic video from playlist: {video_url} - {e}")
                # Optionally, inform the user about problematic videos
                # await ctx.send(f"Could not add one video from the playlist: {video_url}")

        await ctx.send(f"```Added {added_count} songs from the playlist to the queue!```")

        if not (voice_client.is_playing() or voice_client.is_paused()):
            await play_next_song(ctx) # Start playing if nothing is playing

    except Exception as e:
        await ctx.send(f"Could not process the playlist: {e}")
        print(f"Error processing playlist: {e}")


@bot.command(name='skip', help='Skips the current song')
async def skip(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client and voice_client.is_playing():
        await ctx.send("```Skipping current song...```")
        voice_client.stop() # This triggers the 'after' callback to play the next song
    else:
        await ctx.send("The bot is not playing anything to skip.")

@bot.command(name='pause', help='Pauses the current song')
async def pause(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await ctx.send("```Song paused.```")
    else:
        await ctx.send("The bot is not playing anything to pause.")

@bot.command(name='resume', help='Resumes the paused song')
async def resume(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await ctx.send("```Song resumed.```")
    else:
        await ctx.send("The bot was not playing anything before this or is not paused.")

@bot.command(name='stop', help='Stops the current song and clears the queue')
async def stop(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
        voice_client.stop() # Stops playback
        deq.clear() # Clear the queue
        await ctx.send("```Playback stopped and queue cleared.```")
    else:
        await ctx.send("The bot is not playing anything to stop.")

@bot.command(name='list', aliases=['queue', 'q'], help='Shows the current song queue')
async def list_dequeue(ctx):
    if not deq:
        await ctx.send("```The song queue is empty!```")
        return

    string_builder = "```Current Queue:\n"
    for index, song_info in enumerate(deq):
        string_builder += f"{index}. {song_info['title']}\n"
    string_builder += "```"
    await ctx.send(string_builder)

@bot.command(name='remove', help='Removes a specific song from the queue by its number. Usage: !remove <number>')
async def remove_from_queue(ctx, argument: int):
    try:
        if 0 <= argument < len(deq):
            removed_song = deq[argument]
            del deq[argument]
            await ctx.send(f"```Removed '{removed_song['title']}' (position {argument}) from the queue.```")
        else:
            await ctx.send(f"```Invalid queue position. Please use a number between 0 and {len(deq) - 1}.```")
    except Exception as e:
        await ctx.send(f"```An error occurred while trying to remove the song: {e}```")
        print(f"Error in !remove: {e}")

@bot.command(name='clearqueue', aliases=['cq'], help='Removes all items from the song queue')
async def clear_queue(ctx):
    deq.clear()
    await ctx.send('```All items removed from the song queue.```')

@bot.command(name='roll20', help='Rolls a twenty-sided dice')
async def roll_20(ctx):
    random_number = random.randint(1, 20)
    await ctx.send(f'```The number generated is: {random_number}```')

async def main():
    try:
        print("Starting bot...")
        await bot.start(DISCORD_TOKEN)
    except discord.LoginFailure:
        print("Login failed. Check your DISCORD_TOKEN in .env file and Discord Developer Portal.")
    except Exception as e:
        print(f"An unexpected error occurred during bot run: {e}")
    finally:
        print("Bot closing...")
        await bot.close()

# --- Run the bot ---
if __name__ == "__main__":
    print("Attempting to run bot...")
    try:
        # Use asyncio.run() to manage the event loop for your async main function
        asyncio.run(main())
    except discord.LoginFailure:
        print("Login failed. Check your DISCORD_TOKEN in .env file and Discord Developer Portal.")
    except Exception as e:
        print(f"An unexpected error occurred during bot run: {e}")
