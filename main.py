import discord
from discord.ext import commands
from PIL import Image
import io
import os
import pytesseract
import re
import asyncio
import json
from flask import Flask
from threading import Thread

app = Flask('')


@app.route('/')
def home():
    return "Bot is running"


def run():
    app.run(host='0.0.0.0', port=8080)


def keep_alive():
    t = Thread(target=run)
    t.start()


# Initialize the bot
intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.reactions = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

SCORES_FILE = 'scores.json'
current_boss = None
current_start_date = None
current_end_date = None


# Function to save scores to a JSON file
def save_scores():
    with open(SCORES_FILE, 'w') as file:
        json.dump(scores, file)


# Function to load scores from a JSON file
def load_scores():
    if os.path.exists(SCORES_FILE):
        with open(SCORES_FILE, 'r') as file:
            loaded_scores = json.load(file)
            valid_scores = {}
            for user_id, score in loaded_scores.items():
                member = bot.get_user(int(user_id))
                if member:
                    valid_scores[int(user_id)] = score
                else:
                    print(f"User with ID {user_id} not found.")
            return valid_scores
    return {}


# Store scores in a dictionary {user_id: score}
scores = load_scores()


@bot.command()
async def load(ctx):
    global scores
    scores = load_scores()
    await ctx.send("Scores loaded from file.")
    await asyncio.sleep(5)
    await delete_messages_except_first(ctx.channel)
    leaderboard = await generate_leaderboard(ctx.guild)
    await ctx.send(leaderboard)


async def record_score(user_id, score):
    global scores
    scores[user_id] = score
    save_scores()


# Function to extract text from an image using pytesseract
def extract_text_from_image(image_data):
    image = Image.open(io.BytesIO(image_data))
    text = pytesseract.image_to_string(image)
    return text


# Function to extract score from the text using regex (assuming scores are formatted like "Score: 12345")
def extract_score_from_text(text):
    match = re.search(r'Best.*?(\d+\.?\d*)B', text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.online)
    print(f'Logged in as {bot.user}')


# Function to display the leaderboard
async def generate_leaderboard(guild):
    global scores, current_boss, current_start_date
    if not scores:
        return f"## Leaderboard for {current_boss} ({current_start_date})\n" + "No scores submitted yet."
    sorted_scores = sorted(scores.items(),
                           key=lambda item: item[1],
                           reverse=True)
    leaderboard_entries = []
    for index, (user_id, score) in enumerate(sorted_scores):
        print(user_id)
        print(type(user_id))
        member = guild.get_member(user_id)
        if member:
            leaderboard_entries.append(
                f"{index + 1}. **{member.display_name}:** {score}B")
        else:
            leaderboard_entries.append(
                f"{index + 1}. **User not found:** {score}B")
    return f"## Leaderboard for {current_boss} ({current_start_date})\n" + "\n".join(
        leaderboard_entries)


@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return
    if message.channel.name == 'ee-leaderboards':
        for attachment in message.attachments:
            if attachment.filename.endswith(('png', 'jpg', 'jpeg')):
                image_data = await attachment.read()
                text = extract_text_from_image(image_data)
                best_score = extract_score_from_text(text)
                if best_score is not None:

                    confirmation_message = await message.channel.send(
                        f"High score found: {best_score}B. Is this correct?")
                    await confirmation_message.add_reaction('✅')
                    await confirmation_message.add_reaction('❌')

                    def check(reaction, user):
                        return user == message.author and str(
                            reaction.emoji) in ['✅', '❌']

                    try:
                        reaction, user = await bot.wait_for('reaction_add',
                                                            timeout=15.0,
                                                            check=check)
                    except asyncio.TimeoutError:
                        await message.channel.send(
                            'No reaction received. Please try again.')
                        await asyncio.sleep(5)
                        await delete_messages_except_first(message.channel)
                        leaderboard = await generate_leaderboard(message.guild)
                        await message.channel.send(leaderboard)

                    else:
                        if str(reaction.emoji) == '✅':
                            current_score = scores.get(message.author.id, 0)
                            if best_score > current_score:
                                await record_score(message.author.id,
                                                   best_score)
                                # scores[message.author.id] = best_score
                                await message.channel.send(
                                    f"Best score of {best_score}B recorded for {message.author.display_name}"
                                )
                            else:
                                await message.channel.send(
                                    f"Submitted score {best_score}B is not higher than the current best score of {current_score}B for {message.author.display_name}."
                                )
                        elif str(reaction.emoji) == '❌':
                            await message.channel.send(
                                "Score entry cancelled. Please try again or contact a leader to enter the score manually."
                            )
                    # Send updated leaderboard
                    await asyncio.sleep(5)
                    await delete_messages_except_first(message.channel)
                    leaderboard = await generate_leaderboard(message.guild)
                    await message.channel.send(leaderboard)
                else:
                    await message.channel.send(
                        "Could not find a Best Score in the screenshot.")
                    await asyncio.sleep(5)
                    await delete_messages_except_first(message.channel)
                    leaderboard = await generate_leaderboard(message.guild)
                    await message.channel.send(leaderboard)

    await bot.process_commands(message)


@bot.command()
async def enter(ctx, member: discord.Member, score: float):
    if ctx.channel.name == 'ee-leaderboards':
        if discord.utils.get(ctx.author.roles, name="Leader"):
            if score <= 0:
                await ctx.send("Score must be a positive number.")
                return

            current_score = scores.get(member.id, 0)
            if current_score == 0 or score > current_score:
                await record_score(member.id, score)
                # scores[member.id] = score
                await ctx.send(
                    f"Score of {score}B recorded for {member.display_name}")
            else:
                await ctx.send(
                    f"The provided score {score}B is not higher than the current best score of {current_score}B for {member.display_name}."
                )
            await asyncio.sleep(5)
            await delete_messages_except_first(ctx.channel)
            leaderboard = await generate_leaderboard(ctx.guild)
            await ctx.send(leaderboard)
        else:
            await ctx.send("You do not have permission to use this command.")
            await asyncio.sleep(5)
            await delete_messages_except_first(ctx.channel)
            leaderboard = await generate_leaderboard(ctx.guild)
            await ctx.send(leaderboard)


@enter.error
async def enter_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please provide a member and a score.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid member or score format.")
    elif isinstance(error, commands.CommandInvokeError):
        await ctx.send("An error occurred while processing the command.")


@bot.command()
async def clean(ctx):
    if ctx.channel.name == 'ee-leaderboards':
        await delete_messages_except_first(ctx.channel)
        leaderboard = await generate_leaderboard(ctx.guild)
        await ctx.send(leaderboard)


@bot.command()
async def reset(ctx):
    if ctx.channel.name == 'ee-leaderboards':
        if discord.utils.get(ctx.author.roles, name="Leader"):
            global current_boss, current_start_date, current_end_date
            # Ask for the boss's name
            await ctx.send("Please enter the name of the boss:")
            try:
                boss_name_message = await bot.wait_for(
                    'message',
                    timeout=30.0,
                    check=lambda m: m.author == ctx.author and m.channel == ctx
                    .channel)
                boss_name = boss_name_message.content

                # Ask for the start date
                await ctx.send(
                    "Please enter the start date (e.g., January 1, 2024):")
                start_date_message = await bot.wait_for(
                    'message',
                    timeout=30.0,
                    check=lambda m: m.author == ctx.author and m.channel == ctx
                    .channel)
                start_date = start_date_message.content

                # Ask for the end date
                await ctx.send(
                    "Please enter the end date (e.g., January 8, 2024):")
                end_date_message = await bot.wait_for(
                    'message',
                    timeout=30.0,
                    check=lambda m: m.author == ctx.author and m.channel == ctx
                    .channel)
                end_date = end_date_message.content

                # Confirmation
                confirmation_message = await ctx.send(
                    f"Leaderboard for {boss_name} ({start_date} - {end_date}). Is this correct?"
                )
                await confirmation_message.add_reaction('✅')
                await confirmation_message.add_reaction('❌')

                def check(reaction, user):
                    return user == ctx.author and str(
                        reaction.emoji) in ['✅', '❌']

                try:
                    reaction, user = await bot.wait_for('reaction_add',
                                                        timeout=15.0,
                                                        check=check)
                except asyncio.TimeoutError:
                    await ctx.send('No reaction received. Reset canceled.')
                    await delete_messages_except_first(ctx.channel)
                    leaderboard = await generate_leaderboard(ctx.guild)
                    await ctx.send(leaderboard)
                    return
                else:
                    if str(reaction.emoji) == '✅':
                        # Clear scores
                        scores.clear()
                        await ctx.send("Scores cleared.")
                        current_boss = boss_name
                        current_start_date = start_date
                        current_end_date = end_date
                        await ctx.send(
                            f"Boss set to {boss_name} with start date {start_date} and end date {end_date}"
                        )

                        # Delete all messages except the first one
                        await delete_messages_except_first(ctx.channel)

                        # Generate and send new leaderboard
                        leaderboard = await generate_leaderboard(ctx.guild)
                        await ctx.send(leaderboard)

                    else:
                        await ctx.send("Reset canceled.")
                        await asyncio.sleep(5)
                        await delete_messages_except_first(ctx.channel)
                        leaderboard = await generate_leaderboard(ctx.guild)
                        await ctx.send(leaderboard)
            except asyncio.TimeoutError:
                await ctx.send("No response received. Reset canceled.")
                await asyncio.sleep(5)
                await delete_messages_except_first(ctx.channel)
                leaderboard = await generate_leaderboard(ctx.guild)
                await ctx.send(leaderboard)
        else:
            await ctx.send("You do not have permission to use this command.")
            await asyncio.sleep(5)
            await delete_messages_except_first(ctx.channel)
            leaderboard = await generate_leaderboard(ctx.guild)
            await ctx.send(leaderboard)


async def delete_messages_except_first(channel):
    messages = []
    async for message in channel.history(limit=None):
        messages.append(message)
    for message in messages[:-1]:
        await message.delete()


@bot.command()
async def update(ctx, user: discord.Member, new_score: float):
    if ctx.channel.name == 'ee-leaderboards':
        if discord.utils.get(ctx.author.roles, name="Leader"):
            global scores
            user_id = user.id
            if user_id in scores:
                scores[user_id] = new_score
                save_scores()
                await ctx.send(
                    f"Score for {user.display_name} updated to {new_score}.")
                await asyncio.sleep(5)
                await delete_messages_except_first(ctx.channel)
                leaderboard = await generate_leaderboard(ctx.guild)
                await ctx.send(leaderboard)
            else:
                await ctx.send("User not found in the leaderboard.")
                await asyncio.sleep(5)
                await delete_messages_except_first(ctx.channel)
                leaderboard = await generate_leaderboard(ctx.guild)
                await ctx.send(leaderboard)
        else:
            await ctx.send("You do not have permission to use this command.")
            await asyncio.sleep(5)
            await delete_messages_except_first(ctx.channel)
            leaderboard = await generate_leaderboard(ctx.guild)
            await ctx.send(leaderboard)


@bot.command()
async def delete(ctx, position: int):
    if ctx.channel.name == 'ee-leaderboards':
        if discord.utils.get(ctx.author.roles, name="Leader"):
            global scores
            if position > 0 and position <= len(scores):
                sorted_scores = sorted(scores.items(),
                                       key=lambda x: x[1],
                                       reverse=True)
                user_id_to_remove = sorted_scores[position - 1][0]
                del scores[user_id_to_remove]
                save_scores()
                await ctx.send(
                    f"Entry {position} removed from the leaderboard.")
                await asyncio.sleep(5)
                await delete_messages_except_first(ctx.channel)
                leaderboard = await generate_leaderboard(ctx.guild)
                await ctx.send(leaderboard)
            else:
                await ctx.send(
                    "Invalid entry number. Please specify a valid position.")
                await asyncio.sleep(5)
                await delete_messages_except_first(ctx.channel)
                leaderboard = await generate_leaderboard(ctx.guild)
                await ctx.send(leaderboard)
        else:
            await ctx.send("You do not have permission to use this command.")
            await asyncio.sleep(5)
            await delete_messages_except_first(ctx.channel)
            leaderboard = await generate_leaderboard(ctx.guild)
            await ctx.send(leaderboard)


keep_alive()
my_secret = os.environ['DISCORD_BOT_TOKEN']
bot.run(my_secret)