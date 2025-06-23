
import discord
from discord.ext import commands, tasks
import aiosqlite
import asyncio
import json
import random
import datetime
from PIL import Image, ImageDraw, ImageFont
import io
import os
from typing import Optional, Callable, Any

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

class DiscordBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.db_path = 'bot_database.db'

    async def setup_hook(self):
        await self.setup_database()
        birthday_check.start()

    async def setup_database(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Users table for leveling
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    guild_id INTEGER,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 0,
                    messages INTEGER DEFAULT 0
                )
            ''')

            # Tickets table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    guild_id INTEGER,
                    channel_id INTEGER,
                    status TEXT DEFAULT 'open',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Giveaways table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS giveaways (
                    giveaway_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    channel_id INTEGER,
                    message_id INTEGER,
                    prize TEXT,
                    winner_count INTEGER,
                    end_time TIMESTAMP,
                    host_id INTEGER,
                    participants TEXT DEFAULT '[]'
                )
            ''')

            # Birthdays table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS birthdays (
                    user_id INTEGER PRIMARY KEY,
                    guild_id INTEGER,
                    birth_date TEXT,
                    birth_year INTEGER
                )
            ''')

            # Logs table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    log_type TEXT,
                    user_id INTEGER,
                    channel_id INTEGER,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Diamond currency table (for mini games only)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS diamonds (
                    user_id INTEGER PRIMARY KEY,
                    guild_id INTEGER,
                    balance INTEGER DEFAULT 0,
                    last_daily TIMESTAMP,
                    daily_streak INTEGER DEFAULT 0,
                    total_earned INTEGER DEFAULT 0,
                    multiplier REAL DEFAULT 1.0
                )
            ''')

            # Giftcard table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS giftcards (
                    user_id INTEGER PRIMARY KEY,
                    guild_id INTEGER,
                    balance REAL DEFAULT 0.0
                )
            ''')

            # Channel configuration table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS channel_config (
                    guild_id INTEGER,
                    channel_type TEXT,
                    channel_id INTEGER,
                    PRIMARY KEY (guild_id, channel_type)
                )
            ''')

            await db.commit()

bot = DiscordBot()

# AUTOMATIC CHANNEL CONFIGURATION - Set your channel IDs here
DEFAULT_CHANNELS = {
    "ticket": int(os.getenv("TICKET_CHANNEL_ID", "0")),
    "general": int(os.getenv("GENERAL_CHANNEL_ID", "0")),
    "minigames": int(os.getenv("MINIGAMES_CHANNEL_ID", "0")),
    "convert": int(os.getenv("CONVERT_CHANNEL_ID", "0")),
    "daily": int(os.getenv("DAILY_CHANNEL_ID", "0")),
    "transcript": int(os.getenv("TRANSCRIPT_CHANNEL_ID", "0"))
}

# Helper function to get channel IDs (automatic from environment or database fallback)
async def get_channel_config(guild_id: int) -> dict:
    # First try to use environment variables (automatic configuration)
    config = {}
    for channel_type, channel_id in DEFAULT_CHANNELS.items():
        if channel_id > 0:  # Valid channel ID
            config[channel_type] = channel_id
    
    # If no environment variables set, fall back to database
    if not config:
        async with aiosqlite.connect(bot.db_path) as db:
            async with db.execute(
                "SELECT channel_type, channel_id FROM channel_config WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                results = await cursor.fetchall()
                config = {channel_type: channel_id for channel_type, channel_id in results}
    
    return config

async def set_channel_config(guild_id: int, channel_type: str, channel_id: int):
    async with aiosqlite.connect(bot.db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO channel_config (guild_id, channel_type, channel_id) VALUES (?, ?, ?)",
            (guild_id, channel_type, channel_id)
        )
        await db.commit()

# Birthday checker task
@tasks.loop(hours=24)
async def birthday_check():
    today = datetime.datetime.now().strftime("%m-%d")

    async with aiosqlite.connect(bot.db_path) as db:
        async with db.execute(
            "SELECT user_id, guild_id, birth_year FROM birthdays WHERE birth_date = ?",
            (today,)
        ) as cursor:
            birthdays = await cursor.fetchall()

    for user_id, guild_id, birth_year in birthdays:
        guild = bot.get_guild(guild_id)
        user = guild.get_member(user_id) if guild else None

        if user and guild:
            age_text = ""
            if birth_year:
                age = datetime.datetime.now().year - birth_year
                age_text = f" (turning {age})"

            embed = discord.Embed(
                title="🎂 Happy Birthday!",
                description=f"It's {user.mention}'s birthday today{age_text}! 🎉",
                color=0xff69b4
            )

            # Send to designated general channel
            config = await get_channel_config(guild_id)
            general_channel_id = config.get("general")
            channel = guild.get_channel(general_channel_id) if general_channel_id else None
            if not channel:
                channel = discord.utils.get(guild.text_channels, name="general")
                if not channel:
                    channel = guild.text_channels[0] if guild.text_channels else None

            if channel:
                await channel.send(embed=embed)

# Helper functions for Diamond system (mini games only)
async def get_user_diamonds(user_id: int, guild_id: int) -> int:
    async with aiosqlite.connect(bot.db_path) as db:
        async with db.execute(
            "SELECT balance FROM diamonds WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        ) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

async def add_diamonds(user_id: int, guild_id: int, amount: int):
    async with aiosqlite.connect(bot.db_path) as db:
        await db.execute('''
            INSERT OR REPLACE INTO diamonds (user_id, guild_id, balance, total_earned)
            VALUES (?, ?, 
                COALESCE((SELECT balance FROM diamonds WHERE user_id = ? AND guild_id = ?), 0) + ?,
                COALESCE((SELECT total_earned FROM diamonds WHERE user_id = ? AND guild_id = ?), 0) + ?)
        ''', (user_id, guild_id, user_id, guild_id, amount, user_id, guild_id, amount))
        await db.commit()

async def remove_diamonds(user_id: int, guild_id: int, amount: int) -> bool:
    current_balance = await get_user_diamonds(user_id, guild_id)
    if current_balance >= amount:
        async with aiosqlite.connect(bot.db_path) as db:
            await db.execute(
                "UPDATE diamonds SET balance = balance - ? WHERE user_id = ? AND guild_id = ?",
                (amount, user_id, guild_id)
            )
            await db.commit()
        return True
    return False

# Button View Classes
class Button3DView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

class TicketView(Button3DView):
    @discord.ui.button(label="🎫 Open Support Ticket", style=discord.ButtonStyle.primary, emoji="📨", custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        user = interaction.user

        # Check if user already has an open ticket
        async with aiosqlite.connect(bot.db_path) as db:
            async with db.execute(
                "SELECT channel_id FROM tickets WHERE user_id = ? AND guild_id = ? AND status = 'open'",
                (user.id, guild.id)
            ) as cursor:
                existing = await cursor.fetchone()

        if existing:
            channel = guild.get_channel(existing[0])
            if channel:
                await interaction.followup.send(f"You already have an open ticket: {channel.mention}", ephemeral=True)
                return

        # Create ticket channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        config = await get_channel_config(guild.id)
        ticket_channel_id = config.get("ticket")
        ticket_channel = guild.get_channel(ticket_channel_id) if ticket_channel_id else None
        category = ticket_channel.category if ticket_channel else None

        channel = await guild.create_text_channel(
            f"ticket-{user.name}",
            overwrites=overwrites,
            category=category
        )

        # Save to database
        async with aiosqlite.connect(bot.db_path) as db:
            await db.execute(
                "INSERT INTO tickets (user_id, guild_id, channel_id) VALUES (?, ?, ?)",
                (user.id, guild.id, channel.id)
            )
            await db.commit()

        embed = discord.Embed(
            title="🎉 Support Ticket Created!",
            description=f"Welcome {user.mention}! Please describe your issue and our team will assist you.",
            color=0x00ff88,
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="🆔 Ticket ID", value=f"`{channel.name}`", inline=True)
        embed.add_field(name="⏰ Created", value=f"<t:{int(datetime.datetime.now().timestamp())}:R>", inline=True)
        embed.set_footer(text="✨ PCRP Support Team")

        close_view = CloseTicketView()
        await channel.send(embed=embed, view=close_view)

        success_embed = discord.Embed(
            title="✅ Ticket Successfully Created!",
            description=f"🎫 Your support ticket is ready: {channel.mention}",
            color=0x2ECC71
        )
        await interaction.followup.send(embed=success_embed, ephemeral=True)

class CloseTicketView(Button3DView):
    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        guild = interaction.guild

        # Create transcript before closing
        config = await get_channel_config(guild.id)
        transcript_channel_id = config.get("transcript")
        transcript_channel = guild.get_channel(transcript_channel_id) if transcript_channel_id else None

        if transcript_channel:
            # Get ticket info from database
            async with aiosqlite.connect(bot.db_path) as db:
                async with db.execute(
                    "SELECT user_id, created_at FROM tickets WHERE channel_id = ?",
                    (channel.id,)
                ) as cursor:
                    ticket_info = await cursor.fetchone()

            # Collect messages for transcript
            messages = []
            async for message in channel.history(limit=None, oldest_first=True):
                if not message.author.bot or message.embeds or message.attachments:
                    timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    content = message.content or "[Embed/Attachment]"
                    messages.append(f"[{timestamp}] {message.author}: {content}")

            # Create transcript content
            transcript_content = f"""
TICKET TRANSCRIPT - {channel.name}
=============================================
User: <@{ticket_info[0] if ticket_info else 'Unknown'}>
Created: {ticket_info[1] if ticket_info else 'Unknown'}
Closed: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Channel: #{channel.name}
=============================================

{chr(10).join(messages)}
"""

            # Send transcript to transcript channel
            transcript_embed = discord.Embed(
                title="🎫 Ticket Transcript",
                description=f"Transcript for ticket: **{channel.name}**",
                color=0x3498db,
                timestamp=datetime.datetime.now()
            )
            
            if ticket_info:
                user = guild.get_member(ticket_info[0])
                if user:
                    transcript_embed.add_field(name="👤 User", value=user.mention, inline=True)
                    transcript_embed.add_field(name="📅 Created", value=ticket_info[1], inline=True)
            
            transcript_embed.add_field(name="🔒 Closed By", value=interaction.user.mention, inline=True)

            # Save transcript as text file if too long
            if len(transcript_content) > 2000:
                transcript_file = discord.File(
                    io.StringIO(transcript_content),
                    filename=f"transcript-{channel.name}-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
                )
                await transcript_channel.send(embed=transcript_embed, file=transcript_file)
            else:
                transcript_embed.add_field(
                    name="📝 Messages",
                    value=f"```{transcript_content[-1000:]}```",
                    inline=False
                )
                await transcript_channel.send(embed=transcript_embed)

        # Update database
        async with aiosqlite.connect(bot.db_path) as db:
            await db.execute(
                "UPDATE tickets SET status = 'closed' WHERE channel_id = ?",
                (channel.id,)
            )
            await db.commit()

        await interaction.response.send_message("📝 Transcript saved! Ticket will be deleted in 10 seconds...")
        await asyncio.sleep(10)
        await channel.delete()

class AllFeaturesView(Button3DView):
    @discord.ui.button(label="🎂 Set Birthday", style=discord.ButtonStyle.secondary, emoji="🎂", custom_id="set_birthday")
    async def set_birthday(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BirthdayModal())

    @discord.ui.button(label="📈 Check Level", style=discord.ButtonStyle.primary, emoji="📊", custom_id="check_level")
    async def check_level(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        async with aiosqlite.connect(bot.db_path) as db:
            async with db.execute(
                "SELECT xp, level, messages FROM users WHERE user_id = ? AND guild_id = ?",
                (interaction.user.id, interaction.guild.id)
            ) as cursor:
                result = await cursor.fetchone()

        if not result:
            embed = discord.Embed(
                title="📊 Your Stats",
                description="You haven't sent any messages yet! Start chatting to gain XP!",
                color=0xe74c3c
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        xp, level, messages = result
        xp_needed = (level + 1) * 100

        embed = discord.Embed(title="📊 Your Level Stats", color=0x2ECC71)
        embed.add_field(name="🎯 Level", value=f"```{level}```", inline=True)
        embed.add_field(name="⚡ XP", value=f"```{xp}/{xp_needed}```", inline=True)
        embed.add_field(name="💬 Messages", value=f"```{messages}```", inline=True)

        progress = min(xp / xp_needed, 1.0) * 100
        embed.add_field(name="📈 Progress", value=f"```{progress:.1f}% to next level```", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="🏆 Leaderboard", style=discord.ButtonStyle.success, emoji="🏆", custom_id="leaderboard")
    async def show_leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        async with aiosqlite.connect(bot.db_path) as db:
            async with db.execute(
                "SELECT user_id, level, xp FROM users WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 10",
                (interaction.guild.id,)
            ) as cursor:
                results = await cursor.fetchall()

        if not results:
            await interaction.followup.send("No data found!", ephemeral=True)
            return

        embed = discord.Embed(title="🏆 Server Leaderboard", color=0xffd700)

        medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7

        for i, (user_id, level, xp) in enumerate(results, 1):
            user = bot.get_user(user_id)
            name = user.display_name if user else "Unknown User"
            embed.add_field(
                name=f"{medals[i-1]} #{i} {name}",
                value=f"Level {level} • {xp} XP",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

class GiveawayView(Button3DView):
    @discord.ui.button(label="🎉 Enter Giveaway", style=discord.ButtonStyle.success, custom_id="enter_giveaway")
    async def enter_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("You've entered the giveaway! Good luck! 🍀", ephemeral=True)

class BirthdayModal(discord.ui.Modal, title="🎂 Set Your Birthday"):
    def __init__(self):
        super().__init__()

    birthday_date = discord.ui.TextInput(
        label="Birthday Date (MM-DD)",
        placeholder="Enter your birthday (e.g., 12-25)",
        required=True,
        max_length=5
    )

    birth_year = discord.ui.TextInput(
        label="Birth Year (Optional)",
        placeholder="Enter your birth year (e.g., 1995)",
        required=False,
        max_length=4
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Validate date format
            datetime.datetime.strptime(self.birthday_date.value, "%m-%d")

            year = None
            if self.birth_year.value:
                year = int(self.birth_year.value)
                if year < 1900 or year > datetime.datetime.now().year:
                    await interaction.response.send_message("❌ Invalid birth year!", ephemeral=True)
                    return

            async with aiosqlite.connect(bot.db_path) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO birthdays (user_id, guild_id, birth_date, birth_year) VALUES (?, ?, ?, ?)",
                    (interaction.user.id, interaction.guild.id, self.birthday_date.value, year)
                )
                await db.commit()

            success_embed = discord.Embed(
                title="🎂 Birthday Set Successfully!",
                description=f"Your birthday has been set to {self.birthday_date.value}",
                color=0x00ff88
            )
            if year:
                success_embed.add_field(name="Birth Year", value=year, inline=True)

            await interaction.response.send_message(embed=success_embed, ephemeral=True)

        except ValueError:
            await interaction.response.send_message("❌ Invalid date format! Use MM-DD (e.g., 12-25)", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error setting birthday: {str(e)}", ephemeral=True)

class ChannelConfigModal(discord.ui.Modal, title="⚙️ Configure Bot Channels"):
    def __init__(self):
        super().__init__()

    ticket_channel = discord.ui.TextInput(
        label="🎫 Ticket Channel ID",
        placeholder="Channel ID for ticket system",
        required=True
    )

    general_channel = discord.ui.TextInput(
        label="💬 General Channel ID",
        placeholder="Channel ID for general announcements",
        required=True
    )

    minigames_channel = discord.ui.TextInput(
        label="🎮 Minigames Channel ID",
        placeholder="Channel ID for Diamond mini games",
        required=True
    )

    transcript_channel = discord.ui.TextInput(
        label="📝 Transcript Channel ID",
        placeholder="Channel ID for ticket transcripts",
        required=True
    )

    daily_channel = discord.ui.TextInput(
        label="🎁 Daily Channel ID",
        placeholder="Channel ID for daily rewards",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            guild = interaction.guild
            
            # Validate channel IDs
            channels_to_validate = [
                ("ticket", self.ticket_channel.value),
                ("general", self.general_channel.value),
                ("minigames", self.minigames_channel.value),
                ("transcript", self.transcript_channel.value),
                ("daily", self.daily_channel.value)
            ]

            validated_channels = {}
            for channel_type, channel_id_str in channels_to_validate:
                try:
                    channel_id = int(channel_id_str)
                    channel = guild.get_channel(channel_id)
                    if not channel:
                        await interaction.response.send_message(f"❌ {channel_type.title()} channel not found! Make sure the bot has access to it.", ephemeral=True)
                        return
                    validated_channels[channel_type] = channel_id
                except ValueError:
                    await interaction.response.send_message(f"❌ Invalid {channel_type} channel ID format!", ephemeral=True)
                    return

            # Auto-set convert channel to same as general channel
            validated_channels["convert"] = validated_channels["general"]

            # Save to database
            for channel_type, channel_id in validated_channels.items():
                await set_channel_config(guild.id, channel_type, channel_id)

            success_embed = discord.Embed(
                title="✅ Channels Configured Successfully!",
                description="All bot channels have been set up.\n*Convert channel automatically set to General channel.*",
                color=0x00ff88
            )
            
            for channel_type, channel_id in validated_channels.items():
                channel = guild.get_channel(channel_id)
                success_embed.add_field(
                    name=f"{channel_type.title()} Channel",
                    value=f"{channel.mention}",
                    inline=True
                )

            await interaction.response.send_message(embed=success_embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ Error configuring channels: {str(e)}", ephemeral=True)

# MINI GAMES WITH DIAMOND SYSTEM (RESTRICTED TO MINIGAMES CHANNEL)
@bot.tree.command(name="coinflip", description="🪙 Play coin toss - Guess Heads or Tails to win 100 Diamonds!")
@discord.app_commands.describe(choice="Choose Heads or Tails")
@discord.app_commands.choices(choice=[
    discord.app_commands.Choice(name="Heads", value="heads"),
    discord.app_commands.Choice(name="Tails", value="tails")
])
async def coinflip(interaction: discord.Interaction, choice: discord.app_commands.Choice[str]):
    # Check channel restriction
    config = await get_channel_config(interaction.guild.id)
    minigames_channel_id = config.get("minigames")
    
    if not minigames_channel_id:
        embed = discord.Embed(
            title="❌ Bot Not Configured!",
            description="Please use `/configure` to set up bot channels first!",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if interaction.channel.id != minigames_channel_id:
        embed = discord.Embed(
            title="❌ Wrong Channel!",
            description=f"This command can only be used in <#{minigames_channel_id}>",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    result = random.choice(["heads", "tails"])
    won = choice.value == result

    embed = discord.Embed(
        title="🪙 Coin Flip Results",
        color=0x00ff88 if won else 0xe74c3c
    )

    embed.add_field(name="🎯 Your Choice", value=f"```{choice.name}```", inline=True)
    embed.add_field(name="🪙 Result", value=f"```{result.title()}```", inline=True)

    if won:
        await add_diamonds(interaction.user.id, interaction.guild.id, 100)
        embed.add_field(name="🎉 Result", value="```🎉 YOU WON! 🎉```", inline=False)
        embed.add_field(name="💎 Reward", value="```+100 Diamonds```", inline=True)

        new_balance = await get_user_diamonds(interaction.user.id, interaction.guild.id)
        embed.add_field(name="💰 New Balance", value=f"```{new_balance:,}```", inline=True)
    else:
        embed.add_field(name="😔 Result", value="```❌ You Lost!```", inline=False)
        embed.add_field(name="💎 Reward", value="```No reward```", inline=True)
        embed.add_field(name="💡 Tip", value="```Try again - no cost to play!```", inline=True)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="dice", description="🎯 Guess the dice number (1-6) to win 100 Diamonds!")
@discord.app_commands.describe(guess="Your guess (1-6)")
@discord.app_commands.choices(guess=[
    discord.app_commands.Choice(name="1", value=1),
    discord.app_commands.Choice(name="2", value=2),
    discord.app_commands.Choice(name="3", value=3),
    discord.app_commands.Choice(name="4", value=4),
    discord.app_commands.Choice(name="5", value=5),
    discord.app_commands.Choice(name="6", value=6)
])
async def dice(interaction: discord.Interaction, guess: discord.app_commands.Choice[int]):
    # Check channel restriction
    config = await get_channel_config(interaction.guild.id)
    minigames_channel_id = config.get("minigames")
    
    if not minigames_channel_id:
        embed = discord.Embed(
            title="❌ Bot Not Configured!",
            description="Please use `/configure` to set up bot channels first!",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if interaction.channel.id != minigames_channel_id:
        embed = discord.Embed(
            title="❌ Wrong Channel!",
            description=f"This command can only be used in <#{minigames_channel_id}>",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    result = random.randint(1, 6)
    won = guess.value == result

    embed = discord.Embed(
        title="🎲 Dice Roll Results",
        color=0x00ff88 if won else 0xe74c3c
    )

    embed.add_field(name="🎯 Your Guess", value=f"```{guess.value}```", inline=True)
    embed.add_field(name="🎲 Dice Result", value=f"```{result}```", inline=True)

    if won:
        await add_diamonds(interaction.user.id, interaction.guild.id, 100)
        embed.add_field(name="🎉 Result", value="```🎉 PERFECT GUESS! 🎉```", inline=False)
        embed.add_field(name="💎 Reward", value="```+100 Diamonds```", inline=True)

        new_balance = await get_user_diamonds(interaction.user.id, interaction.guild.id)
        embed.add_field(name="💰 New Balance", value=f"```{new_balance:,}```", inline=True)
    else:
        embed.add_field(name="😔 Result", value="```❌ Wrong Guess!```", inline=False)
        embed.add_field(name="💎 Reward", value="```No reward```", inline=True)
        embed.add_field(name="💡 Tip", value="```1 in 6 chance - keep trying!```", inline=True)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="tos_coin", description="🧩 Special ToS Coin Flip - Bet minimum 100 Diamonds to win or lose!")
@discord.app_commands.describe(
    choice="Choose Head or Tail",
    bet="Amount to bet (minimum 100 Diamonds)"
)
@discord.app_commands.choices(choice=[
    discord.app_commands.Choice(name="Head", value="head"),
    discord.app_commands.Choice(name="Tail", value="tail")
])
async def tos_coin(interaction: discord.Interaction, choice: discord.app_commands.Choice[str], bet: int = 100):
    # Check channel restriction
    config = await get_channel_config(interaction.guild.id)
    minigames_channel_id = config.get("minigames")
    
    if not minigames_channel_id:
        embed = discord.Embed(
            title="❌ Bot Not Configured!",
            description="Please use `/configure` to set up bot channels first!",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if interaction.channel.id != minigames_channel_id:
        embed = discord.Embed(
            title="❌ Wrong Channel!",
            description=f"This command can only be used in <#{minigames_channel_id}>",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if bet < 100:
        await interaction.response.send_message("❌ Minimum bet is 100 Diamonds!", ephemeral=True)
        return

    user_balance = await get_user_diamonds(interaction.user.id, interaction.guild.id)

    if user_balance < bet:
        embed = discord.Embed(
            title="❌ Insufficient Diamonds",
            description=f"You need at least {bet:,} Diamonds to place this bet!",
            color=0xe74c3c
        )
        embed.add_field(name="💎 Your Balance", value=f"```{user_balance:,}```", inline=True)
        embed.add_field(name="💎 Required", value=f"```{bet:,}```", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Deduct bet amount first
    await remove_diamonds(interaction.user.id, interaction.guild.id, bet)

    result = random.choice(["head", "tail"])
    won = choice.value == result

    embed = discord.Embed(
        title="🧩 ToS Coin Flip Results",
        description="*Based on Terms of Service Coin*",
        color=0x00ff88 if won else 0xe74c3c
    )

    embed.add_field(name="🎯 Your Pick", value=f"```{choice.name}```", inline=True)
    embed.add_field(name="🪙 ToS Coin Result", value=f"```{result.title()}```", inline=True)
    embed.add_field(name="💰 Bet Amount", value=f"```{bet:,} Diamonds```", inline=True)

    if won:
        winnings = bet * 2
        await add_diamonds(interaction.user.id, interaction.guild.id, winnings)
        embed.add_field(name="🎉 Result", value="```🎉 WINNER! 🎉```", inline=False)
        embed.add_field(name="💎 You Won", value=f"```+{winnings:,} Diamonds```", inline=True)

        new_balance = await get_user_diamonds(interaction.user.id, interaction.guild.id)
        embed.add_field(name="💰 New Balance", value=f"```{new_balance:,}```", inline=True)
    else:
        embed.add_field(name="😔 Result", value="```❌ You Lost!```", inline=False)
        embed.add_field(name="💎 Lost", value=f"```-{bet:,} Diamonds```", inline=True)

        new_balance = await get_user_diamonds(interaction.user.id, interaction.guild.id)
        embed.add_field(name="💰 New Balance", value=f"```{new_balance:,}```", inline=True)

    embed.set_footer(text="🧩 Win = Double your bet, Lose = Lose your bet!")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="diamond_balance", description="Check your Diamond balance from mini games")
async def diamond_balance(interaction: discord.Interaction):
    balance = await get_user_diamonds(interaction.user.id, interaction.guild.id)

    embed = discord.Embed(
        title="💎 Your Diamond Balance",
        color=0x9932cc
    )
    embed.add_field(name="💎 Diamonds", value=f"```{balance:,}```", inline=True)
    embed.add_field(name="💱 Conversion Rate", value="```100 💎 = ₹1```", inline=True)

    rupee_value = balance // 100
    embed.add_field(name="💰 Rupee Value", value=f"```₹{rupee_value}```", inline=True)
    embed.set_footer(text="Earned from mini games only!")

    await interaction.response.send_message(embed=embed)

# XP System (Message Handler)
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Add XP for messages
    xp_gain = random.randint(15, 25)

    async with aiosqlite.connect(bot.db_path) as db:
        # Get current user data
        async with db.execute(
            "SELECT xp, level, messages FROM users WHERE user_id = ? AND guild_id = ?",
            (message.author.id, message.guild.id)
        ) as cursor:
            result = await cursor.fetchone()

        if result:
            current_xp, current_level, messages = result
        else:
            current_xp, current_level, messages = 0, 0, 0

        new_xp = current_xp + xp_gain
        new_messages = messages + 1
        new_level = current_level

        # Check for level up
        xp_needed = (current_level + 1) * 100
        if new_xp >= xp_needed:
            new_level = current_level + 1

            # Level up notification
            embed = discord.Embed(
                title="🎉 Level Up!",
                description=f"{message.author.mention} reached level {new_level}!",
                color=0x00ff88
            )
            await message.channel.send(embed=embed, delete_after=5)

        # Update database
        await db.execute('''
            INSERT OR REPLACE INTO users (user_id, guild_id, xp, level, messages)
            VALUES (?, ?, ?, ?, ?)
        ''', (message.author.id, message.guild.id, new_xp, new_level, new_messages))
        await db.commit()

    await bot.process_commands(message)

# Slash Commands
@bot.tree.command(name="level", description="Check your level")
async def level(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user

    async with aiosqlite.connect(bot.db_path) as db:
        async with db.execute(
            "SELECT xp, level, messages FROM users WHERE user_id = ? AND guild_id = ?",
            (target.id, interaction.guild.id)
        ) as cursor:
            result = await cursor.fetchone()

    if not result:
        await interaction.response.send_message("No data found for this user!", ephemeral=True)
        return

    xp, level, messages = result
    xp_needed = (level + 1) * 100

    embed = discord.Embed(title=f"📊 {target.display_name}'s Level", color=0x2ECC71)
    embed.add_field(name="🎯 Level", value=f"```{level}```", inline=True)
    embed.add_field(name="⚡ XP", value=f"```{xp}/{xp_needed}```", inline=True)
    embed.add_field(name="💬 Messages", value=f"```{messages}```", inline=True)

    progress = min(xp / xp_needed, 1.0) * 100
    embed.add_field(name="📈 Progress", value=f"```{progress:.1f}% to next level```", inline=False)
    embed.set_thumbnail(url=target.display_avatar.url)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="Show server leaderboard")
async def leaderboard(interaction: discord.Interaction):
    async with aiosqlite.connect(bot.db_path) as db:
        async with db.execute(
            "SELECT user_id, level, xp FROM users WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 10",
            (interaction.guild.id,)
        ) as cursor:
            results = await cursor.fetchall()

    if not results:
        await interaction.response.send_message("No data found!", ephemeral=True)
        return

    embed = discord.Embed(title="🏆 Server Leaderboard", color=0xffd700)

    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7

    for i, (user_id, level, xp) in enumerate(results, 1):
        user = bot.get_user(user_id)
        name = user.display_name if user else "Unknown User"
        embed.add_field(
            name=f"{medals[i-1]} #{i} {name}",
            value=f"Level {level} • {xp} XP",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="birthday", description="Set your birthday")
@discord.app_commands.describe(
    date="Your birthday (MM-DD format)",
    year="Birth year (optional)"
)
async def set_birthday(interaction: discord.Interaction, date: str, year: Optional[int] = None):
    try:
        datetime.datetime.strptime(date, "%m-%d")

        async with aiosqlite.connect(bot.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO birthdays (user_id, guild_id, birth_date, birth_year) VALUES (?, ?, ?, ?)",
                (interaction.user.id, interaction.guild.id, date, year)
            )
            await db.commit()

        embed = discord.Embed(
            title="🎂 Birthday Set!",
            description=f"Your birthday has been set to {date}",
            color=0xff69b4
        )
        if year:
            embed.add_field(name="Birth Year", value=year, inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except ValueError:
        await interaction.response.send_message("Invalid date format! Use MM-DD (e.g., 12-25)", ephemeral=True)

@bot.tree.command(name="giveaway", description="Create a giveaway")
@discord.app_commands.describe(
    prize="What are you giving away?",
    duration="Duration in minutes",
    winners="Number of winners"
)
async def giveaway(interaction: discord.Interaction, prize: str, duration: int, winners: int = 1):
    end_time = datetime.datetime.now() + datetime.timedelta(minutes=duration)

    embed = discord.Embed(
        title="🎉 GIVEAWAY! 🎉",
        description=f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** <t:{int(end_time.timestamp())}:R>",
        color=0xff6b6b
    )
    embed.set_footer(text=f"Hosted by {interaction.user}")

    view = GiveawayView()
    await interaction.response.send_message(embed=embed, view=view)

    message = await interaction.original_response()

    async with aiosqlite.connect(bot.db_path) as db:
        await db.execute(
            "INSERT INTO giveaways (guild_id, channel_id, message_id, prize, winner_count, end_time, host_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (interaction.guild.id, interaction.channel.id, message.id, prize, winners, end_time, interaction.user.id)
        )
        await db.commit()

# SETUP COMMANDS
@bot.tree.command(name="configure", description="Configure bot channels for your server")
async def configure_bot(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need Administrator permissions to configure the bot!", ephemeral=True)
        return
    
    await interaction.response.send_modal(ChannelConfigModal())

@bot.tree.command(name="setup", description="Set up all bot features (run /configure first)")
async def setup_bot(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need Administrator permissions to set up the bot!", ephemeral=True)
        return

    guild = interaction.guild
    config = await get_channel_config(guild.id)

    if not config:
        await interaction.response.send_message("❌ Please run `/configure` first to set up bot channels!", ephemeral=True)
        return

    # Set up ticket system
    ticket_channel_id = config.get("ticket")
    if ticket_channel_id:
        ticket_channel = guild.get_channel(ticket_channel_id)
        if ticket_channel:
            embed = discord.Embed(
                title="🎫 Support Tickets",
                description="Click the button below to create a support ticket!",
                color=0x3498db
            )
            view = TicketView()
            await ticket_channel.send(embed=embed, view=view)

    # Set up welcome message in general
    general_channel_id = config.get("general")
    if general_channel_id:
        general_channel = guild.get_channel(general_channel_id)
        if general_channel:
            welcome_embed = discord.Embed(
                title="🎉 Bot Features Active!",
                description=f"""
**Available Features:**
🎫 **Tickets** - Create support tickets
🎉 **Giveaways** - Host exciting giveaways  
📈 **Leveling** - Gain XP and level up
🎂 **Birthdays** - Never miss celebrations
💎 **Mini Games** - Play games to earn Diamonds!

**Mini Game Commands (Use in <#{config.get('minigames', 'minigames-channel')}>):**
`/coinflip` - Free coin toss game
`/dice` - Free dice guessing game  
`/tos_coin` - High stakes betting game
`/diamond_balance` - Check your Diamond balance

**Other Commands:**
`/giveaway` - Create a giveaway
`/level` - Check your level
`/leaderboard` - View top users
`/birthday` - Set your birthday
`/configure` - Reconfigure bot channels
                """,
                color=0x00ff88
            )
            view = AllFeaturesView()
            await general_channel.send(embed=welcome_embed, view=view)

    await interaction.response.send_message("✅ Bot setup complete! All features are now active.", ephemeral=True)

@bot.tree.command(name="ticket", description="Set up ticket system")
@discord.app_commands.describe(channel="Channel to send the ticket panel")
async def ticket_setup(interaction: discord.Interaction, channel: discord.TextChannel):
    embed = discord.Embed(
        title="🎫 Support Ticket System",
        description="Need help? Click the button below to create a private support ticket!",
        color=0x2ECC71
    )
    embed.set_footer(text="✨ PCRP Support Team")

    view = TicketView()
    await channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Ticket system set up!", ephemeral=True)

# Bot Events
@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# Error handling
@bot.event
async def on_error(event, *args, **kwargs):
    print(f'An error occurred in {event}: {args}, {kwargs}')

# Run the bot with your token
if __name__ == "__main__":
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("❌ ERROR: DISCORD_BOT_TOKEN not found!")
        print("Please add your Discord bot token to Replit Secrets:")
        print("1. Go to Secrets tab in left sidebar")
        print("2. Add key: DISCORD_BOT_TOKEN")
        print("3. Add value: your_actual_bot_token_here")
        exit(1)
    
    bot.run(token)
