import sys
import io
import json
import re
from datetime import datetime as dt
from dateutil import parser as dateparser
from os.path import exists
import discord
from discord.ext import tasks
import aiohttp
from cbotdata import CBotData

# For stripping tags from html '<>'
#html_tag_regex = re.compile('<.*?>')
# Thank you based stack-overflow gods...
# Here: https://stackoverflow.com/a/56490838/13542651
# And here: https://stackoverflow.com/a/12982689/13542651
html_tag_regex = re.compile('<.*?>|/&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-fA-F]{1,6})')
def strip_tags(raw_html):
    return re.sub(html_tag_regex, '', raw_html)

def pretty_date(date: str):
    return dateparser.parse(date).astimezone().strftime("%b %d, %Y  %-I:%M%p")

print(f'arg[1]: {sys.argv[1]}')

if (len(sys.argv) < 2):
    print('Please provide a path to a configuration JSON, exiting...')
    exit(2)

config_filename = sys.argv[1]

if not exists(config_filename):
    print(f'Config file \"{config_filename}\" could not be found, exiting...')
    exit(2)

canvas_config = None
discord_config = None
postgres_config = None
with open(config_filename, 'r') as config_file:
    config = json.load(config_file)
    canvas_config = config['Canvas']
    discord_config = config['Discord']
    postgres_config = config['Postgres']



class CBotClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # attributes go here
        self.base_url = canvas_config['Base_Url']
        self.data = None

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
        if 'Debug_Channel_Id' in discord_config:
            channel = self.get_channel(discord_config['Debug_Channel_Id'])
            await channel.send(str)

    async def debug_upload_json_as_file_attachment(self, js):
        if 'Debug_Channel_Id' in discord_config:
            if not js is None:
                channel = self.get_channel(discord_config['Debug_Channel_Id'])
                with io.BytesIO(json.dumps(js, indent=4, sort_keys=True, ensure_ascii=False).encode('utf-8')) as json_bytes:
                    await channel.send(file=discord.File(json_bytes, 'api_response.json'))

    async def _canvas_request(self, endpoint: str):
        async with aiohttp.ClientSession() as canvas_session:
            canvas_session.headers.add('Authorization', 'Bearer ' + canvas_config['API_Token'])
            print(f'{dt.now()} GET: {self.base_url + endpoint}')
            async with canvas_session.get(self.base_url + endpoint) as response:
                if response.status == 200:
                    return await response.json()
        return None

    # Creates a post for an assignment
    async def _post_assignment(self, assignment):
        embed = discord.Embed(
            title = assignment['name'], 
            url = assignment['html_url'],
            color = discord.Color.from_str('#841617'),
            description=strip_tags(assignment['description']))

        embed.add_field(name='Created On', value=pretty_date(assignment['created_at']), inline = False)
        embed.add_field(name='Unlocks On', value=pretty_date(assignment['unlock_at']), inline = False)
        embed.add_field(name='Due On', value=pretty_date(assignment['due_at']), inline = False)

        channel = self.get_channel(discord_config['Channel_Id'])
        await channel.send(content='Your instructor has posted a new assignment...', embed=embed)

    async def _post_submission(self, assignment, submission):
        author = "Anonymous"
        thumb_url = None
        description = ""
        if 'submission_comments' in submission:
            if (len(submission['submission_comments']) > 0):
                description = submission['submission_comments'][0]['comment']
                if 'author' in submission['submission_comments'][0]:
                    if 'display_name' in submission['submission_comments'][0]['author']:
                        author = submission['submission_comments'][0]['author']['display_name']
                    if 'avatar_image_url' in submission['submission_comments'][0]['author']:
                        thumb_url = submission['submission_comments'][0]['author']['avatar_image_url']

        sub_embed = discord.Embed(
            title = assignment['name'] + " Submitted!",
            url = submission['preview_url'],
            color = discord.Color.dark_blue(),
            description = description
        )

        if not thumb_url is None:
            sub_embed.set_thumbnail(url=thumb_url)

        sub_embed.add_field(name='Author', value=author, inline=False)
        sub_embed.add_field(name='Attachments', value=str(len(submission['attachments'])), inline=False)
        sub_embed.add_field(name='Attempt', value=submission['attempt'], inline=False)
        sub_embed.add_field(name='Timing', value="Late!" if submission['late'] else 'On time!', inline=False)
        sub_embed.add_field(name='Submitted On', value=pretty_date(submission['submitted_at']), inline=False)

        channel = self.get_channel(discord_config['Channel_Id'])
        await channel.send(content="A new submission has been posted...", embed=sub_embed)

    @tasks.loop(seconds=300)
    async def check_canvas_background_task(self):
        
        # TO-DO: Move this into the database (register tracked courses per user in a table)
        course_id = canvas_config['Course_Ids'][0]

        # Fetch stored assignments from the database
        stored_assignments = await self.data.get_assignments(course_id=course_id)

        as_js = await self._canvas_request('api/v1/courses/' + str(course_id) + '/assignments?include[]=submission')
        #await self.debug_upload_json_as_file_attachment(as_js)

        if not as_js is None:
            for assignment in as_js:
                assignment_id = assignment['id']
                # If we have not seen this assignment before
                if not (any(stored_assignment['canvas_id'] == assignment_id for stored_assignment in stored_assignments)):
                    # Store info about it in the database
                    await self.data.new_assignment(
                        assignment_id,
                        assignment['course_id'],
                        assignment['name'],
                        strip_tags(assignment['description']),
                        assignment['html_url'],
                        dateparser.parse(assignment['created_at']),
                        dateparser.parse(assignment['unlock_at']),
                        dateparser.parse(assignment['due_at']),
                    )

                    # Create a post for the assignment on discord
                    await self._post_assignment(assignment)

                # Check for new submissions
                if (assignment['submission']['attempt'] > 0):
                    
                    submission = await self._canvas_request('/api/v1/courses/' + str(course_id) + '/assignments/' + str(assignment_id) + '/submissions/self?include[]=submission_comments')
                    #await self.debug_upload_json_as_file_attachment(su_js)
                    submission_id = submission['id']

                    stored_submissions = await self.data.get_submissions(assignment_id)

                    if not (any(stored_submission['canvas_id'] == submission_id for stored_submission in stored_submissions)):
                        # Store info about it in the database
                        await self.data.new_submission(
                            submission_id,
                            submission['assignment_id'],
                            submission['attempt'],
                            submission['late'],
                            dateparser.parse(submission['submitted_at'])
                        )

                        # Create a post for the submission on discord
                        await self._post_submission(assignment, submission)
                    

    @check_canvas_background_task.before_loop
    async def before_check_canvas_task(self):
        # Wait for the bot to log in
        await self.wait_until_ready()
        self.data = await CBotData.create(postgres_config['Host'], postgres_config['Database'], postgres_config['User'], postgres_config['Pass'])
        await self.data.initialize_database()


# To respond to specific message content, we require message_content intent
intents = discord.Intents.default()
intents.message_content = True

client = CBotClient(intents = intents)
client.run(discord_config['Bot_Token'])