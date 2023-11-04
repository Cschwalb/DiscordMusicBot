import asyncio
import random

import discord
import yt_dlp.YoutubeDL
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import yt_dlp as youtube_dl
from _collections import deque

class Queue:
    def __init__(self, *elements):
        self._elements = deque(elements)

    def __len__(self):
        return len(self._elements)

    def __iter__(self):
        while len(self) > 0:
            yield self.dequeue()

    def enqueue(self, element):
        self._elements.append(element)

    def dequeue(self):
        return self._elements.popleft()


load_dotenv()
# Get the API token from the .env file.
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
songQueue = Queue()
intents = discord.Intents().all()
client = discord.Client(intents=intents)
bot = commands.Bot(command_prefix='!', intents=intents)

youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'restrictfilenames': True,
    'noplaylist': True, # perhaps change to false
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # bind to ipv4 since ipv6 addresses cause issues sometimes
    # sourced from medium.com
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=.9):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = ""

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]
        filename = data['title'] if stream else ytdl.prepare_filename(data)
        return filename

    @classmethod
    async def cleanupMusic(cls, ctx, filename):
        try:
            os.remove(filename)
            await ctx.send('deleted file')
        except:
            await ctx.send('cant remove file')


@bot.command(name='join', help='Tells the bot to join the voice channel')
async def join(ctx):
    if not ctx.message.author.voice:
        await ctx.send("{} is not connected to a voice channel".format(ctx.message.author.name))
        return
    else:
        channel = ctx.message.author.voice.channel
    await channel.connect()


@bot.command(name='leave', help='tells bot to leave the voice channel')
async def leave(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_connected():
        await voice_client.disconnect()
    else:
        await ctx.send("The bot is not connected to a voice channel.")


@bot.command(name='add', help='adds to playlist')
async def addToList(ctx, url):
    print(url)
    server = ctx.message.guild
    voice_channel = server.voice_client
    async with ctx.typing():
        url = analyze_input(url)
        filename = await YTDLSource.from_url(url=url, loop=bot.loop)
        songQueue.enqueue(filename)
        print("added file to enqueue")
        print(filename)
        await ctx.send('Filename added to queue:  {}'.format(filename))


@bot.command(name='p', help='plays song from youtube or link')
async def playNow(ctx, url):
    server = ctx.message.guild
    voice_channel = server.voice_client
    if not voice_channel.is_playing():
        async with ctx.typing():
            url = analyze_input(url)
            filename = await YTDLSource.from_url(url = url, loop = bot.loop)
            print('playing {}'.format(filename))
            await ctx.send('Filename added to play now!:  {}'.format(filename))
            await play_music(ctx, filename)
            await ctx.send('[+]Now playing[+] {}'.format(filename))
            while voice_channel.is_playing() is True:
                await asyncio.sleep(1)
        await ctx.send('Done with song!')
    else:
        await ctx.send("Already playing a song! adding to queue, use !play to use that queue")
        await addToList(ctx, url)


@bot.command(name='play', help='play list of songs')
async def play_list(ctx):
    server = ctx.message.guild
    voice_channel = server.voice_client
    if not voice_channel.is_playing():
        async with ctx.typing():
            if len(songQueue) > 0:
                for song in list(songQueue):
                    await play_music(ctx, song)
                    await ctx.send('[+]Now playing[+] {}'.format(song))
                    while voice_channel.is_playing() is True:
                        await asyncio.sleep(1)
            else:

                await ctx.send('no songs queued')
    else:
        await ctx.send('playing a song already.  Cannot update queue at this time.')


def analyze_input(analysis):
    output = ""
    if "http" in analysis:
        print('url analyzed!')
        output = analysis
    else:
        output = search_youtube(analysis)
    return output


def search_youtube(keyword) -> str:  # thank you youtube
    try:
        with youtube_dl.YoutubeDL(ytdl_format_options) as ydl:
            info = ydl.extract_info('ytsearch:' + keyword + ' --max-downloads 1', download=False)['entries'][0] # grab the first instance
    except Exception:
        print(str(Exception))
        return 'ERROR'
    return info['webpage_url'] # subject to change as youtube is a pain...


@bot.command(name='playsingle', help='To play song')
async def play(ctx, url):
    server = ctx.message.guild
    voice_channel = server.voice_client
    async with ctx.typing():
        filename = await YTDLSource.from_url(url, loop=bot.loop)
        songQueue.enqueue(filename)
        print("added song to queue")
        await ctx.send('added new file to queue')
        while songQueue.__len__() > 0:
            url = songQueue.dequeue()
            print(url)
            await play_music(ctx, url)
            await ctx.send('[+]Now playing[+] {}'.format(url))
            if songQueue.__len__() > 0:  # just do a check to avoid any exceptions
                songQueue.dequeue()
                await ctx.send('dequeued a song')


@bot.command(name='playnow', help='plays song or adds to queue')
async def play_now(ctx, url):
    server = ctx.message.guild
    voice_channel = server.voice_client
    url = analyze_input(url)
    filename = await YTDLSource.from_url(url=url, loop=bot.loop)
    if voice_channel.is_playing():
        async with ctx.typing():
            await ctx.send('Song is playing!  adding to queue')
            songQueue.enqueue(filename)
    else:
        async with ctx.typing():
            await ctx.send('Song is added to queue!  Starting play!')
            songQueue.enqueue(filename)
            print(filename)
            print('added to queue')
            while len(songQueue) > 0:
                filename = songQueue.dequeue()
                print(filename)
                print("From test app")
                await play_music(ctx, filename)
                await ctx.send('[+]Now playing[+] {}'.format(filename))
                while voice_channel.is_playing() is True:
                    await asyncio.sleep(2)
                await ctx.send('Done with song!')


@bot.command(name='cleanup', help='Cleans up webm files')
async def remove_files(ctx):
    async with ctx.typing():
        files = os.listdir('.')  # thank you stackoverflow
        for file in files:
            if file.endswith('.webm'):
                os.remove(file)
                await ctx.send('Bot deleting one file!')


async def play_music(ctx, song):
    try:
        server = ctx.message.guild
        voice_channel = server.voice_client
        async with ctx.typing():
            voice_channel.play(discord.FFmpegPCMAudio(executable="ffmpeg.exe", source=song))
    except Exception:
        print(str(Exception))
        await ctx.send('Bot not in channel')


@bot.command(name='skip', help='This command skips the song') # because we have a loop pausing it will end the song
async def skip(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        await voice_client.pause()
    else:
        await ctx.send("The bot is not playing anything at the moment.")


@bot.command(name='resume', help='Resumes the song')
async def resume(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_paused():
        await voice_client.resume()
    else:
        await ctx.send("The bot was not playing anything before this. Use play command")


@bot.command(name='stop', help='Stops the song')
async def stop(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        await voice_client.stop()
    else:
        await ctx.send("The bot is not playing anything at the moment.")


@bot.command(name='roll20', help='rolls a twenty sided dices to see what we get')
async def roll_20(ctx):
    randomNumber = random.randint(0, 20)
    await ctx.send(f'The number generated is:  {randomNumber}')


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)