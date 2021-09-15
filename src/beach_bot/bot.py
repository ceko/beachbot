import discord, logging
from discord.ext import commands, tasks
from discord import utils as dutils
import re, asyncio
import youtube_dl
from .queue import Video, Queue
from .player import Player

logger = logging.getLogger(__name__)

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0' # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn',
    'before_options': '-copyts -err_detect ignore_err -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.2):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def extract_info(cls, query, *, loop=None):
        def do_extract(query):
            if 'https://' in query or 'http://' in query:
                return ytdl.extract_info(query, download=False)
            else:
                return ytdl.extract_info(f'ytsearch:{query}', download=False)

        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: do_extract(query))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        return data

    @classmethod
    async def from_video(cls, video:Video):
        return cls(discord.FFmpegPCMAudio(video.url, **ffmpeg_options), data=video.data, volume=Player.volume/100)

    @classmethod
    async def from_url(cls, url, *, data=None, loop=None):
        if data is None:
            data = cls.extract_info(url, loop)

        filename = data['url']
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class Bot:
    token = None
    client = None

    def __init__(self, token):
        self.token = token
        self.client = Client(
            command_prefix='!bb '
        )

        self.client.add_cog(MusicCog(self.client))

    def start(self):
        self.client.run(self.token)

class MusicCog(commands.Cog):
    def __init__(self, client:"Client"):
        self.client = client
        self.check_queue_task = self.check_queue.start()

    @commands.command(
        help="Makes the bot join the specified voice channel. Get the ID by right-clicking on the channel and copying it.",
        brief="Joins voice channel by id."
    )
    async def join_voice(self, ctx, *, channel: discord.VoiceChannel):
        """Joins a voice channel"""
        if ctx.voice_client is not None:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()

    @join_voice.error
    async def join_voice_error(self, ctx, error):
        await ctx.send('Error joining voice channel.')

    @commands.command(
        help="Summons the bot to your voice channel.",
        brief="Summons the bot to your voice channel."
    )
    async def summon(self, ctx):
        """Joins a voice channel"""
        if ctx.author.voice:
            if ctx.voice_client is not None:
                await ctx.voice_client.move_to(ctx.author.voice.channel)
            else:
                await ctx.author.voice.channel.connect()
        else:
            await ctx.send(embed=discord.Embed(
                title="Error Summoning",
                description=f"Use the summon command when you're in a voice channel.",
                color=0xFF5733
            ))

    @summon.error
    async def summon_error(self, ctx, error):
        await ctx.send('Error joining voice channel.')

    @commands.command(
        help="Disconnect the bot from voice.",
        brief="Disconnect the bot from voice."
    )
    async def disconnect(self, ctx):
        """Disconnects from voice"""
        if ctx.voice_client is not None:
            await ctx.voice_client.disconnect()

    @commands.command(
        help="Queue a YouTube video to play in the active voice channel. You can copy the link directly from YouTube or try your luck searching for it.",
        brief="Queue a YouTube video through query or URL."
    )
    async def play(self, ctx, *, url: str):
        async with ctx.typing():
            video_info = await YTDLSource.extract_info(url, loop=self.client.loop)
            video = Video(
                video_info['webpage_url_basename'],
                video_info['url'],
                video_info['title'],
                video_info
            )
            if Queue.has(video):
                await ctx.send(embed=discord.Embed(
                    title="Error Queueing",
                    description=f"Video '{video.title}' already exists in queue. Wait your turn.",
                    color=0xFF5733
                ))
            else:
                Queue.videos.append(video)
                await ctx.send(f'Queued: {video.title}')

            #player = await YTDLSource.from_url(url, loop=self.client.loop)
            #ctx.voice_client.play(
            #    player,
            #    after=lambda e: self.client.loop.create_task(self.queue_video_finished(e))
            #)
            #await self.client.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=player.title))

    @play.error
    async def play_error(self, ctx, error):
        logger.error(error)
        await ctx.send(embed=discord.Embed(
            title="Error Queueing",
            description=f"There was an error queueing the video. Maybe you copied the URL wrong?",
            color=0xFF5733
        ))

    @commands.command(
        help="Changes the bot's voice volume. The range is from 1-200.",
        brief="Changes the bot's voice volume."
    )
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""

        Player.volume = volume
        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        ctx.voice_client.source.volume = Player.volume / 100

    @commands.command(
        help="Skip the current song.",
        brief="Skip the currently playing song and move to the next one."
    )
    async def skip(self, ctx):
        ctx.voice_client.stop()

    @commands.command(
        help="Resets the bot, clearing queues and disconnecting from voice.",
        brief="Resets the bot, clearing queues and disconnecting from voice."
    )
    async def reset(self, ctx):
        Queue.reset()
        if ctx.voice_client is not None:
            ctx.voice_client.stop()
            await ctx.voice_client.disconnect()

    async def queue_video_finished(self, err):
        if err:
            logger.error("Error in video: %s", err)
        await self.client.on_video_finished()

    @tasks.loop(seconds=5)
    async def check_queue(self):
        # only support one voice client because this only runs
        # on one server

        for client in self.client.voice_clients:
            if not client.is_playing() and any(Queue.videos):
                # play next video
                player = await YTDLSource.from_video(Queue.pop())
                client.play(
                    player,
                    after=lambda e: self.client.loop.create_task(self.queue_video_finished(e))
                )
                await self.client.change_presence(
                    activity=discord.Activity(type=discord.ActivityType.listening, name=player.title)
                )

class Client(commands.Bot):
    async def on_ready(self):
        logging.info("Discord bot ready")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="the queue"))

    async def on_video_finished(self):
        logging.info("Video finished")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="the queue"))

    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.user.id: return

        if payload.emoji.name == "BeachClub":
            channel = self.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            await message.add_reaction(dutils.get(self.emojis, name="BeachClub"))

    async def on_message(self, message):
        if message.author == self.user:
            return

        await super().on_message(message)