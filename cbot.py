import sys
import io
import json
from os.path import exists
import discord
from discord.ext import tasks
import aiohttp

print(f'arg[1]: {sys.argv[1]}')

if (len(sys.argv) < 2):
    print('Please provide a path to a configuration JSON, exiting...')
    exit(2)

config_filename = sys.argv[1]

if not exists(config_filename):
    print(f'Config file \"{config_filename}\" could not be found, exiting...')
    exit(2)

config = None
with open(config_filename, 'r') as config_file:
    config = json.load(config_file)


class CBotClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # attributes go here
        self.base_url = config['Canvas_Base_Url']

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.content.startswith('$hello'):
            await message.channel.send('Hello!')

    async def setup_hook(self) -> None:
        # Start background tasks
        self.check_canvas_background_task.start()

    async def debug_post_message(self, str):
        if 'Debug_Channel_Id' in config:
            channel = self.get_channel(config['Debug_Channel_Id'])
            await channel.send(str)

    async def debug_upload_json_as_file_attachment(self, js):
        if 'Debug_Channel_Id' in config:
            if not js is None:
                channel = self.get_channel(config['Debug_Channel_Id'])
                with io.BytesIO(json.dumps(js, indent=4, sort_keys=True, ensure_ascii=False).encode('utf-8')) as json_bytes:
                    await channel.send(file=discord.File(json_bytes, 'api_response.json'))

    @tasks.loop(seconds=300)
    async def check_canvas_background_task(self):

        js = None
        async with aiohttp.ClientSession() as canvas_session:
            canvas_session.headers.add('Authorization', 'Bearer ' + config['Canvas_API_Token'])
            async with canvas_session.get(self.base_url + 'api/v1/courses') as response:
                if response.status == 200:
                    js = await response.json()

        if js is None:
            await self.debug_post_message('Did not receive json from canvas')

        await self.debug_post_message('This message was sent')


    @check_canvas_background_task.before_loop
    async def before_check_canvas_task(self):
        # Wait for the bot to log in
        await self.wait_until_ready()


# To respond to specific message content, we require message_content intent
intents = discord.Intents.default()
intents.message_content = True

client = CBotClient(intents = intents)
client.run(config['Discord_Bot_Token'])