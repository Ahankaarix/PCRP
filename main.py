
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
from typing import Optional

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# Channel IDs
TICKET_CHANNEL_ID = 1386365038411124916
GENERAL_CHANNEL_ID = 1386365076268908564

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

            # Diamond currency table
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
            channel = guild.get_channel(GENERAL_CHANNEL_ID)
            if not channel:
                channel = discord.utils.get(guild.text_channels, name="general")
                if not channel:
                    channel = guild.text_channels[0] if guild.text_channels else None

            if channel:
                await channel.send(embed=embed)

bot = DiscordBot()

# Helper functions for Diamond system
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

async def get_user_giftcard_balance(user_id: int, guild_id: int) -> float:
    async with aiosqlite.connect(bot.db_path) as db:
        async with db.execute(
            "SELECT balance FROM giftcards WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        ) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0.0

# 3D Button View Class
class Button3DView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

class TicketView(Button3DView):
    @discord.ui.button(label="🎫 Open Support Ticket", style=discord.ButtonStyle.primary, emoji="📨", custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Defer the response immediately to prevent timeout
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

        # Try to find tickets category or use the ticket channel's category
        ticket_channel = guild.get_channel(TICKET_CHANNEL_ID)
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
            description=f"""
**Welcome {user.mention}!** 👋

┌─────────────────────────────────────┐
│  **🔹 Your ticket is now active**  │
│                                     │
│  Please describe your issue in      │
│  detail and our team will assist    │
│  you as soon as possible!           │
│                                     │
│  📝 **Tips for faster support:**   │
│  • Be specific about your issue    │
│  • Include screenshots if helpful  │
│  • Mention any error messages      │
└─────────────────────────────────────┘

🔔 **Our team has been notified!**
            """,
            color=0x00ff88,
            timestamp=datetime.datetime.now()
        )
        embed.add_field(
            name="🆔 Ticket ID",
            value=f"`{channel.name}`",
            inline=True
        )
        embed.add_field(
            name="⏰ Created",
            value=f"<t:{int(datetime.datetime.now().timestamp())}:R>",
            inline=True
        )
        embed.add_field(
            name="📊 Status",
            value="```🟢 Active```",
            inline=True
        )
        embed.set_footer(text="✨ PCRP Support Team | We're here to help!")
        embed.set_thumbnail(url="https://img.icons8.com/color/96/000000/checked.png")

        close_view = CloseTicketView()
        await channel.send(embed=embed, view=close_view)

        # Enhanced response message
        success_embed = discord.Embed(
            title="✅ Ticket Successfully Created!",
            description=f"🎫 Your support ticket is ready: {channel.mention}\n\n🚀 Our team will respond shortly!",
            color=0x2ECC71
        )
        await interaction.followup.send(embed=success_embed, ephemeral=True)

class CloseTicketView(Button3DView):
    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        TRANSCRIPT_CHANNEL_ID = 1386368897447493783  # Backup channel

        # Create transcript
        transcript_channel = interaction.guild.get_channel(TRANSCRIPT_CHANNEL_ID)
        if transcript_channel:
            messages = []
            async for msg in channel.history(limit=None, oldest_first=True):
                messages.append(f"[{msg.created_at}] {msg.author}: {msg.content}")

            transcript_content = "\n".join(messages)

            # Save transcript as file
            import io
            transcript_file = io.StringIO(transcript_content)
            file = discord.File(io.BytesIO(transcript_content.encode()), filename=f"ticket-{channel.name}-transcript.txt")

            backup_embed = discord.Embed(
                title="📄 Ticket Transcript",
                description=f"Backup of {channel.name}",
                color=0x3498db
            )
            await transcript_channel.send(embed=backup_embed, file=file)

        async with aiosqlite.connect(bot.db_path) as db:
            await db.execute(
                "UPDATE tickets SET status = 'closed' WHERE channel_id = ?",
                (channel.id,)
            )
            await db.commit()

        await interaction.response.send_message("📄 Transcript created! Ticket will be deleted in 10 seconds...")
        await asyncio.sleep(10)
        await channel.delete()

class MultiPurposeView(Button3DView):
    @discord.ui.button(label="🚨 Report User", style=discord.ButtonStyle.danger, custom_id="report_user")
    async def report_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal())

    @discord.ui.button(label="🔨 Ban Appeal", style=discord.ButtonStyle.secondary, custom_id="ban_appeal")
    async def ban_appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BanAppealModal())

    @discord.ui.button(label="❓ General Question", style=discord.ButtonStyle.primary, custom_id="question")
    async def general_question(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(QuestionModal())

class ReportModal(discord.ui.Modal, title="🚨 Report User"):
    def __init__(self):
        super().__init__()

    user_to_report = discord.ui.TextInput(
        label="User to Report",
        placeholder="Enter username or user ID...",
        required=True,
        max_length=100
    )

    reason = discord.ui.TextInput(
        label="Reason for Report",
        placeholder="Describe the issue in detail...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🚨 User Report Submitted",
            description="Your report has been submitted to the moderation team.",
            color=0xe74c3c
        )
        embed.add_field(name="Reported User", value=self.user_to_report.value, inline=False)
        embed.add_field(name="Reason", value=self.reason.value, inline=False)
        embed.add_field(name="Reporter", value=interaction.user.mention, inline=True)
        embed.timestamp = datetime.datetime.now()

        # Send to moderation channel (you can change this channel ID)
        mod_channel = interaction.guild.get_channel(TICKET_CHANNEL_ID)
        if mod_channel:
            await mod_channel.send(embed=embed)

        await interaction.response.send_message("✅ Report submitted successfully! Creating a support ticket for you...", ephemeral=True)

        # Auto-create ticket for this user
        await self.create_auto_ticket(interaction, "Report Follow-up", f"Report submitted for: {self.user_to_report.value}")

    async def create_auto_ticket(self, interaction: discord.Interaction, ticket_type: str, details: str):
        guild = interaction.guild
        user = interaction.user

        # Create ticket channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        # Try to find tickets category or use the ticket channel's category
        ticket_channel = guild.get_channel(TICKET_CHANNEL_ID)
        category = ticket_channel.category if ticket_channel else None

        channel = await guild.create_text_channel(
            f"ticket-{user.name}-{ticket_type.lower().replace(' ', '')}",
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
            title=f"🎫 {ticket_type} Ticket Created!",
            description=f"""
**Welcome {user.mention}!** 👋

┌─────────────────────────────────────┐
│  **🔹 Auto-Generated Ticket**      │
│                                     │
│  This ticket was automatically      │
│  created after your submission.     │
│  Our team will assist you here.     │
│                                     │
│  📝 **Submission Details:**        │
│  {details}                          │
└─────────────────────────────────────┘

🔔 **Our team has been notified!**
            """,
            color=0x00ff88,
            timestamp=datetime.datetime.now()
        )
        embed.add_field(
            name="🆔 Ticket ID",
            value=f"`{channel.name}`",
            inline=True
        )
        embed.add_field(
            name="⏰ Created",
            value=f"<t:{int(datetime.datetime.now().timestamp())}:R>",
            inline=True
        )
        embed.add_field(
            name="📊 Status",
            value="```🟢 Active```",
            inline=True
        )
        embed.set_footer(text="✨ PCRP Support Team | Auto-Generated Ticket")
        embed.set_thumbnail(url="https://img.icons8.com/color/96/000000/checked.png")

        close_view = CloseTicketView()
        await channel.send(embed=embed, view=close_view)

class BanAppealModal(discord.ui.Modal, title="🔨 Ban Appeal"):
    def __init__(self):
        super().__init__()

    ban_reason = discord.ui.TextInput(
        label="Original Ban Reason",
        placeholder="Why were you banned?",
        required=True,
        max_length=200
    )

    appeal_reason = discord.ui.TextInput(
        label="Why should you be unbanned?",
        placeholder="Explain why you believe the ban should be lifted...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🔨 Ban Appeal Submitted",
            description="Your ban appeal has been submitted for review.",
            color=0xf39c12
        )
        embed.add_field(name="Original Ban Reason", value=self.ban_reason.value, inline=False)
        embed.add_field(name="Appeal Reason", value=self.appeal_reason.value, inline=False)
        embed.add_field(name="User", value=interaction.user.mention, inline=True)
        embed.timestamp = datetime.datetime.now()

        # Send to moderation channel
        mod_channel = interaction.guild.get_channel(TICKET_CHANNEL_ID)
        if mod_channel:
            await mod_channel.send(embed=embed)

        await interaction.response.send_message("✅ Ban appeal submitted! Creating a support ticket for you...", ephemeral=True)

        # Auto-create ticket for this user
        await self.create_auto_ticket(interaction, "Ban Appeal", f"Appeal for ban reason: {self.ban_reason.value}")

    async def create_auto_ticket(self, interaction: discord.Interaction, ticket_type: str, details: str):
        guild = interaction.guild
        user = interaction.user

        # Create ticket channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        # Try to find tickets category or use the ticket channel's category
        ticket_channel = guild.get_channel(TICKET_CHANNEL_ID)
        category = ticket_channel.category if ticket_channel else None

        channel = await guild.create_text_channel(
            f"ticket-{user.name}-{ticket_type.lower().replace(' ', '')}",
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
            title=f"🎫 {ticket_type} Ticket Created!",
            description=f"""
**Welcome {user.mention}!** 👋

┌─────────────────────────────────────┐
│  **🔹 Auto-Generated Ticket**      │
│                                     │
│  This ticket was automatically      │
│  created after your submission.     │
│  Our team will assist you here.     │
│                                     │
│  📝 **Submission Details:**        │
│  {details}                          │
└─────────────────────────────────────┘

🔔 **Our team has been notified!**
            """,
            color=0x00ff88,
            timestamp=datetime.datetime.now()
        )
        embed.add_field(
            name="🆔 Ticket ID",
            value=f"`{channel.name}`",
            inline=True
        )
        embed.add_field(
            name="⏰ Created",
            value=f"<t:{int(datetime.datetime.now().timestamp())}:R>",
            inline=True
        )
        embed.add_field(
            name="📊 Status",
            value="```🟢 Active```",
            inline=True
        )
        embed.set_footer(text="✨ PCRP Support Team | Auto-Generated Ticket")
        embed.set_thumbnail(url="https://img.icons8.com/color/96/000000/checked.png")

        close_view = CloseTicketView()
        await channel.send(embed=embed, view=close_view)

class QuestionModal(discord.ui.Modal, title="❓ General Question"):
    def __init__(self):
        super().__init__()

    subject = discord.ui.TextInput(
        label="Question Subject",
        placeholder="Brief topic of your question...",
        required=True,
        max_length=100
    )

    question = discord.ui.TextInput(
        label="Your Question",
        placeholder="Ask your question in detail...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="❓ Question Submitted",
            description="Your question has been submitted to our team.",
            color=0x3498db
        )
        embed.add_field(name="Subject", value=self.subject.value, inline=False)
        embed.add_field(name="Question", value=self.question.value, inline=False)
        embed.add_field(name="Asked by", value=interaction.user.mention, inline=True)
        embed.timestamp = datetime.datetime.now()

        # Send to general channel or support channel
        support_channel = interaction.guild.get_channel(GENERAL_CHANNEL_ID)
        if support_channel:
            await support_channel.send(embed=embed)

        await interaction.response.send_message("✅ Question submitted! Creating a support ticket for you...", ephemeral=True)

        # Auto-create ticket for this user
        await self.create_auto_ticket(interaction, "General Question", f"Question about: {self.subject.value}")

    async def create_auto_ticket(self, interaction: discord.Interaction, ticket_type: str, details: str):
        guild = interaction.guild
        user = interaction.user

        # Create ticket channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        # Try to find tickets category or use the ticket channel's category
        ticket_channel = guild.get_channel(TICKET_CHANNEL_ID)
        category = ticket_channel.category if ticket_channel else None

        channel = await guild.create_text_channel(
            f"ticket-{user.name}-{ticket_type.lower().replace(' ', '')}",
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
            title=f"🎫 {ticket_type} Ticket Created!",
            description=f"""
**Welcome {user.mention}!** 👋

┌─────────────────────────────────────┐
│  **🔹 Auto-Generated Ticket**      │
│                                     │
│  This ticket was automatically      │
│  created after your submission.     │
│  Our team will assist you here.     │
│                                     │
│  📝 **Submission Details:**        │
│  {details}                          │
└─────────────────────────────────────┘

🔔 **Our team has been notified!**
            """,
            color=0x00ff88,
            timestamp=datetime.datetime.now()
        )
        embed.add_field(
            name="🆔 Ticket ID",
            value=f"`{channel.name}`",
            inline=True
        )
        embed.add_field(
            name="⏰ Created",
            value=f"<t:{int(datetime.datetime.now().timestamp())}:R>",
            inline=True
        )
        embed.add_field(
            name="📊 Status",
            value="```🟢 Active```",
            inline=True
        )
        embed.set_footer(text="✨ PCRP Support Team | Auto-Generated Ticket")
        embed.set_thumbnail(url="https://img.icons8.com/color/96/000000/checked.png")

        close_view = CloseTicketView()
        await channel.send(embed=embed, view=close_view)

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

        embed = discord.Embed(
            title="📊 Your Level Stats",
            color=0x2ECC71
        )
        embed.add_field(name="🎯 Level", value=f"```{level}```", inline=True)
        embed.add_field(name="⚡ XP", value=f"```{xp}/{xp_needed}```", inline=True)
        embed.add_field(name="💬 Messages", value=f"```{messages}```", inline=True)

        progress = min(xp / xp_needed, 1.0) * 100
        embed.add_field(name="📈 Progress", value=f"```{progress:.1f}% to next level```", inline=False)
        embed.set_footer(text=f"Keep chatting to level up!")

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

    @discord.ui.button(label="💎 Check Diamonds", style=discord.ButtonStyle.blurple, emoji="💎", custom_id="check_diamonds")
    async def check_diamonds(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        balance = await get_user_diamonds(interaction.user.id, interaction.guild.id)
        giftcard_balance = await get_user_giftcard_balance(interaction.user.id, interaction.guild.id)
        
        embed = discord.Embed(
            title="💎 Your Diamond Balance",
            color=0x9932cc
        )
        embed.add_field(name="💎 Diamonds", value=f"```{balance:,}```", inline=True)
        embed.add_field(name="🎁 Gift Card", value=f"```₹{giftcard_balance:.2f}```", inline=True)
        embed.add_field(name="💱 Conversion Rate", value="```100 💎 = ₹1```", inline=True)
        
        rupee_value = balance // 100
        embed.add_field(name="💰 Rupee Value", value=f"```₹{rupee_value}```", inline=False)
        embed.set_footer(text="Use /claim_daily to earn more diamonds!")
        
        await interaction.followup.send(embed=embed, ephemeral=True)

class BirthdayModal(discord.ui.Modal, title="🎂 Set Your Birthday"):
    def __init__(self):
        super().__init__()

    birthday_date = discord.ui.TextInput(
        label="Birthday Date (MM-DD)",
        placeholder="Example: 12-25 for December 25th",
        required=True,
        max_length=5
    )

    birth_year = discord.ui.TextInput(
        label="Birth Year (Optional)",
        placeholder="Example: 1995",
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
                    await interaction.response.send_message("❌ Please enter a valid birth year!", ephemeral=True)
                    return

            async with aiosqlite.connect(bot.db_path) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO birthdays (user_id, guild_id, birth_date, birth_year) VALUES (?, ?, ?, ?)",
                    (interaction.user.id, interaction.guild.id, self.birthday_date.value, year)
                )
                await db.commit()

            age_text = f" (born {year})" if year else ""
            embed = discord.Embed(
                title="🎂 Birthday Set Successfully!",
                description=f"Your birthday has been set to **{self.birthday_date.value}**{age_text}\n\nWe'll celebrate with you when the day comes! 🎉",
                color=0x2ECC71
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except ValueError:
            await interaction.response.send_message("❌ Invalid date format! Please use MM-DD (e.g., 12-25)", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ An error occurred. Please try again!", ephemeral=True)

class GiveawayModal(discord.ui.Modal, title="🎉 Create Giveaway"):
    def __init__(self):
        super().__init__()

    prize = discord.ui.TextInput(
        label="Prize",
        placeholder="What are you giving away?",
        required=True,
        max_length=200
    )

    duration = discord.ui.TextInput(
        label="Duration (minutes)",
        placeholder="How long should the giveaway last?",
        required=True,
        max_length=5
    )

    winners = discord.ui.TextInput(
        label="Number of Winners",
        placeholder="How many winners?",
        required=True,
        max_length=2
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            duration_int = int(self.duration.value)
            winners_int = int(self.winners.value)

            if duration_int <= 0 or winners_int <= 0:
                await interaction.response.send_message("❌ Duration and winners must be positive numbers!", ephemeral=True)
                return

            end_time = datetime.datetime.now() + datetime.timedelta(minutes=duration_int)

            embed = discord.Embed(
                title="🎉 GIVEAWAY! 🎉",
                description=f"**Prize:** {self.prize.value}\n**Winners:** {winners_int}\n**Ends:** <t:{int(end_time.timestamp())}:R>",
                color=0xff6b6b
            )
            embed.set_footer(text=f"Hosted by {interaction.user}")

            view = GiveawayView()
            await interaction.response.send_message(embed=embed, view=view)

            message = await interaction.original_response()

            # Save to database
            async with aiosqlite.connect(bot.db_path) as db:
                await db.execute(
                    "INSERT INTO giveaways (guild_id, channel_id, message_id, prize, winner_count, end_time, host_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (interaction.guild.id, interaction.channel.id, message.id, self.prize.value, winners_int, end_time, interaction.user.id)
                )
                await db.commit()

        except ValueError:
            await interaction.response.send_message("❌ Please enter valid numbers for duration and winners!", ephemeral=True)

class GiveawayView(Button3DView):
    @discord.ui.button(label="🎉 Join Giveaway", style=discord.ButtonStyle.success, custom_id="join_giveaway")
    async def join_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        message_id = interaction.message.id
        user_id = interaction.user.id

        async with aiosqlite.connect(bot.db_path) as db:
            async with db.execute(
                "SELECT participants FROM giveaways WHERE message_id = ?",
                (message_id,)
            ) as cursor:
                result = await cursor.fetchone()

            if result:
                participants = json.loads(result[0])
                if user_id in participants:
                    await interaction.response.send_message("You're already participating!", ephemeral=True)
                    return

                participants.append(user_id)
                await db.execute(
                    "UPDATE giveaways SET participants = ? WHERE message_id = ?",
                    (json.dumps(participants), message_id)
                )
                await db.commit()

                await interaction.response.send_message("You've joined the giveaway! 🎉", ephemeral=True)

# DIAMOND SYSTEM SLASH COMMANDS
@bot.tree.command(name="get_conversion", description="View Diamond to gift card conversion rates")
async def get_conversion(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💎 Diamond Conversion Rates",
        description="See how many Diamonds you need for gift cards!",
        color=0x9932cc
    )
    
    embed.add_field(
        name="💱 Conversion Rate",
        value="```100 Diamonds = ₹1```",
        inline=False
    )
    
    # Common conversion examples
    conversions = [
        (500, 5),
        (1000, 10),
        (2500, 25),
        (5000, 50),
        (10000, 100)
    ]
    
    conversion_text = ""
    for diamonds, rupees in conversions:
        conversion_text += f"💎 {diamonds:,} → ₹{rupees}\n"
    
    embed.add_field(
        name="📊 Common Conversions",
        value=f"```{conversion_text}```",
        inline=False
    )
    
    user_balance = await get_user_diamonds(interaction.user.id, interaction.guild.id)
    user_rupee_value = user_balance // 100
    
    embed.add_field(
        name="💰 Your Current Value",
        value=f"```💎 {user_balance:,} = ₹{user_rupee_value}```",
        inline=False
    )
    
    embed.set_footer(text="All values rounded down • No decimals allowed")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="convert_points", description="Convert your Diamonds into a gift card")
@discord.app_commands.describe(amount="Amount of Diamonds to convert (minimum 100)")
async def convert_points(interaction: discord.Interaction, amount: int):
    if amount < 100:
        await interaction.response.send_message("❌ Minimum conversion is 100 Diamonds!", ephemeral=True)
        return
    
    user_balance = await get_user_diamonds(interaction.user.id, interaction.guild.id)
    
    if user_balance < amount:
        await interaction.response.send_message(f"❌ You only have {user_balance:,} Diamonds!", ephemeral=True)
        return
    
    # Convert diamonds to rupees (rounded down)
    rupee_value = amount // 100
    
    if rupee_value == 0:
        await interaction.response.send_message("❌ You need at least 100 Diamonds to convert!", ephemeral=True)
        return
    
    # Remove diamonds and add to gift card balance
    await remove_diamonds(interaction.user.id, interaction.guild.id, amount)
    
    async with aiosqlite.connect(bot.db_path) as db:
        await db.execute('''
            INSERT OR REPLACE INTO giftcards (user_id, guild_id, balance)
            VALUES (?, ?, COALESCE((SELECT balance FROM giftcards WHERE user_id = ? AND guild_id = ?), 0) + ?)
        ''', (interaction.user.id, interaction.guild.id, interaction.user.id, interaction.guild.id, rupee_value))
        await db.commit()
    
    embed = discord.Embed(
        title="✅ Conversion Successful!",
        description=f"You've successfully converted your Diamonds!",
        color=0x00ff88
    )
    embed.add_field(name="💎 Diamonds Used", value=f"```{amount:,}```", inline=True)
    embed.add_field(name="🎁 Gift Card Added", value=f"```₹{rupee_value}```", inline=True)
    
    new_balance = await get_user_diamonds(interaction.user.id, interaction.guild.id)
    new_giftcard = await get_user_giftcard_balance(interaction.user.id, interaction.guild.id)
    
    embed.add_field(name="💎 Remaining Diamonds", value=f"```{new_balance:,}```", inline=True)
    embed.add_field(name="🎁 Total Gift Card", value=f"```₹{new_giftcard:.2f}```", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="convert_giftcard", description="Convert your gift card balance back into Diamonds")
@discord.app_commands.describe(amount="Rupee amount to convert back to Diamonds")
async def convert_giftcard(interaction: discord.Interaction, amount: float):
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
        return
    
    giftcard_balance = await get_user_giftcard_balance(interaction.user.id, interaction.guild.id)
    
    if giftcard_balance < amount:
        await interaction.response.send_message(f"❌ You only have ₹{giftcard_balance:.2f} in gift card balance!", ephemeral=True)
        return
    
    # Convert rupees back to diamonds
    diamonds_to_add = int(amount * 100)  # 1 rupee = 100 diamonds
    
    # Remove from gift card and add diamonds
    async with aiosqlite.connect(bot.db_path) as db:
        await db.execute(
            "UPDATE giftcards SET balance = balance - ? WHERE user_id = ? AND guild_id = ?",
            (amount, interaction.user.id, interaction.guild.id)
        )
        await db.commit()
    
    await add_diamonds(interaction.user.id, interaction.guild.id, diamonds_to_add)
    
    embed = discord.Embed(
        title="✅ Gift Card Converted!",
        description=f"You've successfully converted your gift card back to Diamonds!",
        color=0x00ff88
    )
    embed.add_field(name="🎁 Gift Card Used", value=f"```₹{amount}```", inline=True)
    embed.add_field(name="💎 Diamonds Added", value=f"```{diamonds_to_add:,}```", inline=True)
    
    new_balance = await get_user_diamonds(interaction.user.id, interaction.guild.id)
    new_giftcard = await get_user_giftcard_balance(interaction.user.id, interaction.guild.id)
    
    embed.add_field(name="💎 Total Diamonds", value=f"```{new_balance:,}```", inline=True)
    embed.add_field(name="🎁 Remaining Gift Card", value=f"```₹{new_giftcard:.2f}```", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="convert_currency", description="Simulate Diamond value in different currencies (for reference only)")
@discord.app_commands.describe(currency="Currency to convert to (USD, EUR, GBP, etc.)")
async def convert_currency(interaction: discord.Interaction, currency: str):
    user_balance = await get_user_diamonds(interaction.user.id, interaction.guild.id)
    rupee_value = user_balance // 100
    
    # Sample exchange rates (these would normally come from an API)
    exchange_rates = {
        "USD": 0.012,  # 1 INR = 0.012 USD
        "EUR": 0.011,  # 1 INR = 0.011 EUR
        "GBP": 0.0095, # 1 INR = 0.0095 GBP
        "CAD": 0.016,  # 1 INR = 0.016 CAD
        "AUD": 0.018,  # 1 INR = 0.018 AUD
        "JPY": 1.8,    # 1 INR = 1.8 JPY
    }
    
    currency = currency.upper()
    
    if currency not in exchange_rates:
        available = ", ".join(exchange_rates.keys())
        await interaction.response.send_message(f"❌ Currency not supported! Available: {available}", ephemeral=True)
        return
    
    converted_value = rupee_value * exchange_rates[currency]
    
    embed = discord.Embed(
        title="💱 Currency Conversion Simulation",
        description="⚠️ **This is for reference only - your balance is not converted!**",
        color=0xf39c12
    )
    
    embed.add_field(name="💎 Your Diamonds", value=f"```{user_balance:,}```", inline=True)
    embed.add_field(name="💰 Rupee Value", value=f"```₹{rupee_value}```", inline=True)
    embed.add_field(name=f"🌍 {currency} Value", value=f"```{converted_value:.2f} {currency}```", inline=True)
    
    embed.add_field(
        name="📊 Conversion Rate",
        value=f"```1 INR = {exchange_rates[currency]} {currency}```",
        inline=False
    )
    
    embed.set_footer(text="Note: Exchange rates are approximate and for simulation only")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="claim_daily", description="Claim your daily Diamond reward")
async def claim_daily(interaction: discord.Interaction):
    user_id = interaction.user.id
    guild_id = interaction.guild.id
    now = datetime.datetime.now()
    
    async with aiosqlite.connect(bot.db_path) as db:
        # Get user's daily claim data
        async with db.execute(
            "SELECT last_daily, daily_streak FROM diamonds WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        ) as cursor:
            result = await cursor.fetchone()
        
        if result:
            last_daily_str, current_streak = result
            if last_daily_str:
                last_daily = datetime.datetime.fromisoformat(last_daily_str)
                time_since_last = now - last_daily
                
                # Check if already claimed today
                if time_since_last.total_seconds() < 86400:  # 24 hours
                    time_left = 86400 - time_since_last.total_seconds()
                    hours_left = int(time_left // 3600)
                    minutes_left = int((time_left % 3600) // 60)
                    
                    embed = discord.Embed(
                        title="⏰ Daily Already Claimed",
                        description=f"Come back in {hours_left}h {minutes_left}m to claim again!",
                        color=0xe74c3c
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # Check if within 36 hours to maintain streak
                if time_since_last.total_seconds() <= 129600:  # 36 hours
                    new_streak = current_streak + 1
                else:
                    new_streak = 1  # Reset streak
            else:
                new_streak = 1
        else:
            new_streak = 1
        
        # Calculate reward
        base_reward = 100
        streak_bonus = min(new_streak * 10, 200)  # Max 200 bonus
        total_reward = base_reward + streak_bonus
        
        # Update database
        await db.execute('''
            INSERT OR REPLACE INTO diamonds (user_id, guild_id, balance, last_daily, daily_streak, total_earned)
            VALUES (?, ?, 
                COALESCE((SELECT balance FROM diamonds WHERE user_id = ? AND guild_id = ?), 0) + ?,
                ?, ?,
                COALESCE((SELECT total_earned FROM diamonds WHERE user_id = ? AND guild_id = ?), 0) + ?)
        ''', (user_id, guild_id, user_id, guild_id, total_reward, now.isoformat(), new_streak, user_id, guild_id, total_reward))
        await db.commit()
    
    # Try to send DM
    try:
        dm_embed = discord.Embed(
            title="💎 Daily Reward Claimed!",
            description=f"You've earned {total_reward} Diamonds!",
            color=0x00ff88
        )
        await interaction.user.send(embed=dm_embed)
        dm_status = "✅ DM sent successfully!"
    except:
        dm_status = "❌ Couldn't send DM - check your DM settings!"
    
    embed = discord.Embed(
        title="💎 Daily Reward Claimed!",
        description="Your daily Diamonds have been added to your balance!",
        color=0x00ff88
    )
    embed.add_field(name="💎 Base Reward", value=f"```{base_reward}```", inline=True)
    embed.add_field(name="🔥 Streak Bonus", value=f"```{streak_bonus}```", inline=True)
    embed.add_field(name="💰 Total Earned", value=f"```{total_reward}```", inline=True)
    embed.add_field(name="📅 Current Streak", value=f"```{new_streak} days```", inline=True)
    embed.add_field(name="📬 DM Status", value=dm_status, inline=False)
    
    new_balance = await get_user_diamonds(user_id, guild_id)
    embed.add_field(name="💎 Total Balance", value=f"```{new_balance:,}```", inline=False)
    
    embed.set_footer(text="💡 Claim within 36 hours to maintain your streak!")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="get_points", description="Check Diamond balance for yourself or another user")
@discord.app_commands.describe(user="User to check (leave empty for yourself)")
async def get_points(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    target = user or interaction.user
    
    balance = await get_user_diamonds(target.id, interaction.guild.id)
    giftcard_balance = await get_user_giftcard_balance(target.id, interaction.guild.id)
    
    # Get additional stats
    async with aiosqlite.connect(bot.db_path) as db:
        async with db.execute(
            "SELECT total_earned, daily_streak, multiplier FROM diamonds WHERE user_id = ? AND guild_id = ?",
            (target.id, interaction.guild.id)
        ) as cursor:
            result = await cursor.fetchone()
    
    if result:
        total_earned, daily_streak, multiplier = result
    else:
        total_earned, daily_streak, multiplier = 0, 0, 1.0
    
    embed = discord.Embed(
        title=f"💎 {target.display_name}'s Diamond Stats",
        color=0x9932cc
    )
    embed.add_field(name="💎 Current Balance", value=f"```{balance:,}```", inline=True)
    embed.add_field(name="🎁 Gift Card Balance", value=f"```₹{giftcard_balance:.2f}```", inline=True)
    embed.add_field(name="📊 Total Earned", value=f"```{total_earned:,}```", inline=True)
    embed.add_field(name="🔥 Daily Streak", value=f"```{daily_streak} days```", inline=True)
    embed.add_field(name="⚡ Multiplier", value=f"```{multiplier}x```", inline=True)
    
    rupee_value = balance // 100
    embed.add_field(name="💰 Rupee Value", value=f"```₹{rupee_value}```", inline=True)
    
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.set_footer(text="Use /claim_daily to earn more diamonds!")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="transfer_points", description="Transfer Diamonds to another user")
@discord.app_commands.describe(
    user="User to transfer Diamonds to",
    amount="Amount of Diamonds to transfer"
)
async def transfer_points(interaction: discord.Interaction, user: discord.Member, amount: int):
    if user.id == interaction.user.id:
        await interaction.response.send_message("❌ You can't transfer Diamonds to yourself!", ephemeral=True)
        return
    
    if user.bot:
        await interaction.response.send_message("❌ You can't transfer Diamonds to bots!", ephemeral=True)
        return
    
    if amount <= 0:
        await interaction.response.send_message("❌ Transfer amount must be positive!", ephemeral=True)
        return
    
    sender_balance = await get_user_diamonds(interaction.user.id, interaction.guild.id)
    
    if sender_balance < amount:
        await interaction.response.send_message(f"❌ You only have {sender_balance:,} Diamonds!", ephemeral=True)
        return
    
    # Perform transfer
    await remove_diamonds(interaction.user.id, interaction.guild.id, amount)
    await add_diamonds(user.id, interaction.guild.id, amount)
    
    embed = discord.Embed(
        title="✅ Transfer Successful!",
        description=f"You've transferred Diamonds to {user.mention}!",
        color=0x00ff88
    )
    embed.add_field(name="💎 Amount Transferred", value=f"```{amount:,}```", inline=True)
    embed.add_field(name="👤 Recipient", value=f"```{user.display_name}```", inline=True)
    
    new_sender_balance = await get_user_diamonds(interaction.user.id, interaction.guild.id)
    new_recipient_balance = await get_user_diamonds(user.id, interaction.guild.id)
    
    embed.add_field(name="💎 Your New Balance", value=f"```{new_sender_balance:,}```", inline=True)
    embed.add_field(name="💎 Their New Balance", value=f"```{new_recipient_balance:,}```", inline=True)
    
    # Try to notify recipient via DM
    try:
        dm_embed = discord.Embed(
            title="💎 Diamonds Received!",
            description=f"You received {amount:,} Diamonds from {interaction.user.display_name}!",
            color=0x00ff88
        )
        await user.send(embed=dm_embed)
    except:
        pass  # Ignore if DM fails
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="get_multipliers", description="View your current earning multipliers")
async def get_multipliers(interaction: discord.Interaction):
    async with aiosqlite.connect(bot.db_path) as db:
        async with db.execute(
            "SELECT multiplier, daily_streak FROM diamonds WHERE user_id = ? AND guild_id = ?",
            (interaction.user.id, interaction.guild.id)
        ) as cursor:
            result = await cursor.fetchone()
    
    if result:
        multiplier, daily_streak = result
    else:
        multiplier, daily_streak = 1.0, 0
    
    embed = discord.Embed(
        title="⚡ Your Multipliers",
        description="Here are your current earning bonuses!",
        color=0xf39c12
    )
    
    embed.add_field(name="🎯 Base Multiplier", value=f"```{multiplier}x```", inline=True)
    embed.add_field(name="🔥 Streak Bonus", value=f"```+{min(daily_streak * 10, 200)} per daily```", inline=True)
    embed.add_field(name="📅 Current Streak", value=f"```{daily_streak} days```", inline=True)
    
    # Calculate potential daily reward
    base_daily = 100
    streak_bonus = min(daily_streak * 10, 200)
    total_daily = int((base_daily + streak_bonus) * multiplier)
    
    embed.add_field(name="💎 Next Daily Reward", value=f"```{total_daily} Diamonds```", inline=False)
    
    embed.add_field(
        name="📊 Multiplier Sources",
        value="```• Base: 1.0x\n• Future bonuses coming soon!```",
        inline=False
    )
    
    embed.set_footer(text="Keep your streak going for maximum rewards!")
    await interaction.response.send_message(embed=embed)

# MINI GAMES
@bot.tree.command(name="coinflip", description="🪙 Play coin toss - Guess Heads or Tails to win 100 Diamonds!")
@discord.app_commands.describe(choice="Choose Heads or Tails")
@discord.app_commands.choices(choice=[
    discord.app_commands.Choice(name="Heads", value="heads"),
    discord.app_commands.Choice(name="Tails", value="tails")
])
async def coinflip(interaction: discord.Interaction, choice: discord.app_commands.Choice[str]):
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

@bot.tree.command(name="tos_coin", description="🧩 Special ToS Coin Flip - Pick Head or Tail to win 100 Diamonds!")
@discord.app_commands.describe(choice="Choose Head or Tail")
@discord.app_commands.choices(choice=[
    discord.app_commands.Choice(name="Head", value="head"),
    discord.app_commands.Choice(name="Tail", value="tail")
])
async def tos_coin(interaction: discord.Interaction, choice: discord.app_commands.Choice[str]):
    result = random.choice(["head", "tail"])
    won = choice.value == result
    
    embed = discord.Embed(
        title="🧩 ToS Coin Flip Results",
        description="*Based on Terms of Service Coin*",
        color=0x00ff88 if won else 0xe74c3c
    )
    
    embed.add_field(name="🎯 Your Pick", value=f"```{choice.name}```", inline=True)
    embed.add_field(name="🪙 ToS Coin Result", value=f"```{result.title()}```", inline=True)
    
    if won:
        await add_diamonds(interaction.user.id, interaction.guild.id, 100)
        embed.add_field(name="🎉 Result", value="```🎉 WINNER! 🎉```", inline=False)
        embed.add_field(name="💎 Reward", value="```+100 Diamonds```", inline=True)
        
        new_balance = await get_user_diamonds(interaction.user.id, interaction.guild.id)
        embed.add_field(name="💰 New Balance", value=f"```{new_balance:,}```", inline=True)
    else:
        embed.add_field(name="😔 Result", value="```❌ Better Luck Next Time!```", inline=False)
        embed.add_field(name="💎 Reward", value="```No reward```", inline=True)
        embed.add_field(name="🎮 Note", value="```No Diamonds lost - play again!```", inline=True)
    
    embed.set_footer(text="🧩 Special ToS Edition | No risk, all reward!")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="test_dm", description="📩 Test if the bot can send you Direct Messages")
async def test_dm(interaction: discord.Interaction):
    try:
        test_embed = discord.Embed(
            title="✅ DM Test Successful!",
            description="🎉 The bot can send you Direct Messages!\n\nYou'll receive notifications for:\n• Daily reward claims\n• Diamond transfers\n• Important updates",
            color=0x00ff88
        )
        test_embed.set_footer(text="✨ PCRP Bot | DM Test")
        
        await interaction.user.send(embed=test_embed)
        
        response_embed = discord.Embed(
            title="✅ DM Test Successful!",
            description="Check your Direct Messages - the test was successful!",
            color=0x00ff88
        )
        response_embed.add_field(
            name="📬 DM Status",
            value="```✅ Working perfectly!```",
            inline=False
        )
        response_embed.add_field(
            name="🔔 You'll receive DMs for:",
            value="```• Daily reward claims\n• Diamond transfers\n• Important updates```",
            inline=False
        )
        
        await interaction.response.send_message(embed=response_embed, ephemeral=True)
        
    except discord.Forbidden:
        error_embed = discord.Embed(
            title="❌ DM Test Failed",
            description="I couldn't send you a Direct Message!",
            color=0xe74c3c
        )
        error_embed.add_field(
            name="🔧 How to fix:",
            value="```1. Go to User Settings\n2. Privacy & Safety\n3. Enable 'Direct messages from server members'\n4. Try the test again```",
            inline=False
        )
        error_embed.add_field(
            name="⚠️ Impact:",
            value="```You won't receive notifications for:\n• Daily rewards\n• Diamond transfers\n• Important updates```",
            inline=False
        )
        
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
    
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ DM Test Error",
            description="An unexpected error occurred during the DM test.",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)

# Slash Commands
@bot.tree.command(name="setup", description="Set up all bot features")
async def setup_bot(interaction: discord.Interaction):
    guild = interaction.guild

    # Set up ticket system
    ticket_channel = guild.get_channel(TICKET_CHANNEL_ID)
    if ticket_channel:
        embed = discord.Embed(
            title="🎫 Support Tickets",
            description="Click the button below to create a support ticket!\n\n**3D Modern Design** ✨",
            color=0x3498db
        )
        embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/🎫.png")
        view = TicketView()
        await ticket_channel.send(embed=embed, view=view)

    # Set up welcome message in general
    general_channel = guild.get_channel(GENERAL_CHANNEL_ID)
    if general_channel:
        welcome_embed = discord.Embed(
            title="🎉 Bot Features Active!",
            description="""
**🚀 Available Features:**
🎫 **Tickets** - Create support tickets
🎉 **Giveaways** - Host exciting giveaways  
📈 **Leveling** - Gain XP and level up
🎂 **Birthdays** - Never miss celebrations
📋 **Logging** - Track all server activity
💎 **Diamond System** - Earn and spend Diamonds!

**Diamond Commands:**
`/claim_daily` - Get daily Diamond rewards
`/get_points` - Check Diamond balance
`/coinflip` `/dice` `/tos_coin` - Play mini games
`/convert_points` - Convert to gift cards
`/transfer_points` - Send Diamonds to friends

**Slash Commands:**
`/giveaway` - Create a giveaway
`/level` - Check your level
`/leaderboard` - View top users
`/birthday` - Set your birthday
`/logs` - View recent logs
            """,
            color=0x00ff88
        )
        await general_channel.send(embed=welcome_embed)

    await interaction.response.send_message("✅ Bot setup complete! All features including Diamond system are now active.", ephemeral=True)

@bot.tree.command(name="ticket", description="Set up ticket system")
@discord.app_commands.describe(channel="Channel to send the ticket panel")
async def ticket_setup(interaction: discord.Interaction, channel: discord.TextChannel):
    embed = discord.Embed(
        title="🎫 Support Ticket System",
        description="""
┌─────────────────────────────────────┐
│    **🔹 Need Help? We're Here!**   │
│                                     │
│ 💬 Click the button below to open  │
│    a private support ticket        │
│                                     │
│ ⚡ **Fast Response Time**           │
│ 🔒 **Private & Secure**            │
│ 👥 **Professional Support**        │
└─────────────────────────────────────┘

✨ **What happens next?**
• A private channel will be created
• Our team will be notified instantly
• You'll get personalized assistance
        """,
        color=0x2ECC71,
        timestamp=datetime.datetime.now()
    )

    # Add stylish fields in compact boxes
    embed.add_field(
        name="🌟 Support Hours",
        value="```24/7 Available```",
        inline=True
    )
    embed.add_field(
        name="⏱️ Response Time",
        value="```< 5 minutes```",
        inline=True
    )
    embed.add_field(
        name="📊 Success Rate",
        value="```99.9% Resolved```",
        inline=True
    )

    embed.set_footer(
        text="✨ Powered by PCRP | Premium Support Experience",
        icon_url="https://cdn.discordapp.com/emojis/1234567890123456789.png"
    )
    embed.set_thumbnail(url="https://img.icons8.com/color/96/000000/customer-support.png")

    view = TicketView()
    await channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Stylish ticket system set up!", ephemeral=True)

@bot.tree.command(name="allfeatures", description="Set up comprehensive panel with all bot features")
@discord.app_commands.describe(channel="Channel to send the all-features panel")
async def all_features_setup(interaction: discord.Interaction, channel: discord.TextChannel):
    embed = discord.Embed(
        title="🚀 PCRP Bot Command Center",
        description="""
┌─────────────────────────────────────┐
│    **🔹 All Features in One Place** │
│                                     │
│ 🎂 **Birthday** - Set your birthday │
│ 📈 **Level** - Check your progress  │
│ 🏆 **Leaderboard** - See top users  │
│ 💎 **Diamonds** - Check your wealth │
│                                     │
│ Click any button below to get       │
│ started with our features!          │
└─────────────────────────────────────┘

✨ **Quick Access to Everything!**
        """,
        color=0x00ff88,
        timestamp=datetime.datetime.now()
    )

    embed.add_field(
        name="🎂 Birthdays",
        value="```Set & celebrate```",
        inline=True
    )
    embed.add_field(
        name="📊 Leveling",
        value="```XP & Progress```",
        inline=True
    )
    embed.add_field(
        name="🏆 Leaderboard",
        value="```Top players```",
        inline=True
    )
    embed.add_field(
        name="💎 Diamonds",
        value="```Check balance```",
        inline=True
    )

    embed.set_footer(
        text="✨ Powered by PCRP | All-in-One Command Center",
        icon_url="https://cdn.discordapp.com/emojis/1234567890123456789.png"
    )
    embed.set_thumbnail(url="https://img.icons8.com/color/96/000000/dashboard.png")

    view = AllFeaturesView()
    await channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ All-features panel set up!", ephemeral=True)

@bot.tree.command(name="multipanel", description="Set up multi-purpose panel for reports, appeals, and questions")
@discord.app_commands.describe(channel="Channel to send the multi-purpose panel")
async def multi_panel_setup(interaction: discord.Interaction, channel: discord.TextChannel):
    embed = discord.Embed(
        title="🛠️ Server Support Center",
        description="""
┌─────────────────────────────────────┐
│    **🔹 Multiple Services Hub**    │
│                                     │
│ Choose the appropriate option below │
│ for your specific need:             │
│                                     │
│ 🚨 **Report User** - Report issues │
│ 🔨 **Ban Appeal** - Appeal your ban│
│ ❓ **Questions** - General inquiries│
└─────────────────────────────────────┘

✨ **All submissions are reviewed by our team**
        """,
        color=0x9b59b6,
        timestamp=datetime.datetime.now()
    )

    embed.add_field(
        name="🚨 Report System",
        value="```Report rule violations```",
        inline=True
    )
    embed.add_field(
        name="🔨 Appeal System",
        value="```Contest your ban```",
        inline=True
    )
    embed.add_field(
        name="❓ Q&A System",
        value="```Ask any questions```",
        inline=True
    )

    embed.set_footer(
        text="✨ Powered by PCRP | Multi-Service Support",
        icon_url="https://cdn.discordapp.com/emojis/1234567890123456789.png"
    )
    embed.set_thumbnail(url="https://img.icons8.com/color/96/000000/settings.png")

    view = MultiPurposeView()
    await channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Multi-purpose panel set up!", ephemeral=True)

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

    # Save to database
    async with aiosqlite.connect(bot.db_path) as db:
        await db.execute(
            "INSERT INTO giveaways (guild_id, channel_id, message_id, prize, winner_count, end_time, host_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (interaction.guild.id, interaction.channel.id, message.id, prize, winners, end_time, interaction.user.id)
        )
        await db.commit()

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

    # Create level card
    img = Image.new('RGB', (800, 200), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw progress bar
    bar_width = 600
    bar_height = 30
    bar_x = 100
    bar_y = 150
    progress = min(xp / xp_needed, 1.0)

    # Background bar
    draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], fill=(64, 64, 64))
    # Progress bar
    draw.rectangle([bar_x, bar_y, bar_x + (bar_width * progress), bar_y + bar_height], fill=(0, 255, 136))

    # Text
    draw.text((50, 50), f"{target.display_name}", fill=(255, 255, 255))
    draw.text((50, 80), f"Level {level}", fill=(255, 255, 255))
    draw.text((50, 110), f"XP: {xp}/{xp_needed}", fill=(255, 255, 255))

    # Save image
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    file = discord.File(buffer, filename='level.png')
    await interaction.response.send_message(file=file)

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

    embed = discord.Embed(title="📈 Leaderboard", color=0xffd700)

    for i, (user_id, level, xp) in enumerate(results, 1):
        user = bot.get_user(user_id)
        name = user.display_name if user else "Unknown User"
        embed.add_field(
            name=f"{i}. {name}",
            value=f"Level {level} ({xp} XP)",
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
        # Validate date format
        datetime.datetime.strptime(date, "%m-%d")

        async with aiosqlite.connect(bot.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO birthdays (user_id, guild_id, birth_date, birth_year) VALUES (?, ?, ?, ?)",
                (interaction.user.id, interaction.guild.id, date, year)
            )
            await db.commit()

        await interaction.response.send_message(f"🎂 Birthday set to {date}!", ephemeral=True)

    except ValueError:
        await interaction.response.send_message("Invalid date format! Use MM-DD (e.g., 12-25)", ephemeral=True)

@bot.tree.command(name="logs", description="View recent logs")
async def view_logs(interaction: discord.Interaction, log_type: Optional[str] = None):
    query = "SELECT log_type, user_id, content, timestamp FROM logs WHERE guild_id = ?"
    params = [interaction.guild.id]

    if log_type:
        query += " AND log_type = ?"
        params.append(log_type)

    query += " ORDER BY timestamp DESC LIMIT 10"

    async with aiosqlite.connect(bot.db_path) as db:
        async with db.execute(query, params) as cursor:
            results = await cursor.fetchall()

    if not results:
        await interaction.response.send_message("No logs found!", ephemeral=True)
        return

    embed = discord.Embed(title="📋 Recent Logs", color=0x3498db)

    for log_type, user_id, content, timestamp in results:
        user = bot.get_user(user_id)
        name = user.display_name if user else "Unknown User"
        embed.add_field(
            name=f"{log_type.upper()} - {name}",
            value=f"{content}\n{timestamp}",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

# Event handlers for logging and leveling
@bot.event
async def on_ready():
    print(f'{bot.user} has landed! 🚀')
    print('💎 Diamond System Loaded!')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")

        # Add persistent views for existing buttons
        bot.add_view(TicketView())
        bot.add_view(CloseTicketView())
        bot.add_view(MultiPurposeView())
        bot.add_view(AllFeaturesView())
        bot.add_view(GiveawayView())
        print("✅ Added persistent views for existing buttons")

        # Auto-setup ticket panel
        await auto_setup_ticket_panel()

    except Exception as e:
        print(f"Failed to sync commands: {e}")

async def auto_setup_ticket_panel():
    """Automatically set up both panels when bot starts"""
    for guild in bot.guilds:
        ticket_channel = guild.get_channel(TICKET_CHANNEL_ID)
        if ticket_channel:
            # Delete all old messages in the ticket channel
            try:
                await ticket_channel.purge(limit=100)
                print(f"🧹 Cleared old messages in {ticket_channel.name}")
            except discord.Forbidden:
                print(f"❌ No permission to clear messages in {ticket_channel.name}")
            except Exception as e:
                print(f"❌ Error clearing messages: {e}")
            # PANEL 1: Support Ticket System
            embed1 = discord.Embed(
                title="🎫 Support Ticket System",
                description="""
┌─────────────────────────────────────┐
│    **🔹 Need Help? We're Here!**   │
│                                     │
│ 💬 Click the button below to open  │
│    a private support ticket        │
│                                     │
│ ⚡ **Fast Response Time**           │
│ 🔒 **Private & Secure**            │
│ 👥 **Professional Support**        │
└─────────────────────────────────────┘

✨ **What happens next?**
• A private channel will be created
• Our team will be notified instantly
• You'll get personalized assistance
                """,
                color=0x2ECC71,
                timestamp=datetime.datetime.now()
            )

            embed1.add_field(
                name="🌟 Support Hours",
                value="```24/7 Available```",
                inline=True
            )
            embed1.add_field(
                name="⏱️ Response Time",
                value="```< 5 minutes```",
                inline=True
            )
            embed1.add_field(
                name="📊 Success Rate",
                value="```99.9% Resolved```",
                inline=True
            )

            embed1.set_footer(
                text="✨ Powered by PCRP | Premium Support Experience",
                icon_url="https://cdn.discordapp.com/emojis/1234567890123456789.png"
            )
            embed1.set_thumbnail(url="https://img.icons8.com/color/96/000000/customer-support.png")

            view1 = TicketView()
            await ticket_channel.send(embed=embed1, view=view1)

            # PANEL 2: Multi-Purpose System
            embed2 = discord.Embed(
                title="🛠️ Server Support Center",
                description="""
┌─────────────────────────────────────┐
│    **🔹 Multiple Services Hub**    │
│                                     │
│ Choose the appropriate option below │
│ for your specific need:             │
│                                     │
│ 🚨 **Report User** - Report issues │
│ 🔨 **Ban Appeal** - Appeal your ban│
│ ❓ **Questions** - General inquiries│
└─────────────────────────────────────┘

✨ **All submissions are reviewed by our team**
                """,
                color=0x9b59b6,
                timestamp=datetime.datetime.now()
            )

            embed2.add_field(
                name="🚨 Report System",
                value="```Report rule violations```",
                inline=True
            )
            embed2.add_field(
                name="🔨 Appeal System",
                value="```Contest your ban```",
                inline=True
            )
            embed2.add_field(
                name="❓ Q&A System",
                value="```Ask any questions```",
                inline=True
            )

            embed2.set_footer(
                text="✨ Powered by PCRP | Multi-Service Support",
                icon_url="https://cdn.discordapp.com/emojis/1234567890123456789.png"
            )
            embed2.set_thumbnail(url="https://img.icons8.com/color/96/000000/settings.png")

            view2 = MultiPurposeView()
            await ticket_channel.send(embed=embed2, view=view2)

            print(f"✅ Auto-setup both panels in {guild.name}")

        # PANEL 3: All Features Panel in General Channel
        general_channel = guild.get_channel(GENERAL_CHANNEL_ID)
        if general_channel:
            # Clear old messages in general channel too
            try:
                await general_channel.purge(limit=50)
                print(f"🧹 Cleared old messages in {general_channel.name}")
            except discord.Forbidden:
                print(f"❌ No permission to clear messages in {general_channel.name}")
            except Exception as e:
                print(f"❌ Error clearing messages: {e}")

            embed3 = discord.Embed(
                title="🚀 PCRP Bot Command Center",
                description="""
┌─────────────────────────────────────┐
│    **🔹 All Features in One Place** │
│                                     │
│ 🎂 **Birthday** - Set your birthday │
│ 📈 **Level** - Check your progress  │
│ 🏆 **Leaderboard** - See top users  │
│ 💎 **Diamonds** - Check your wealth │
│                                     │
│ Click any button below to get       │
│ started with our features!          │
└─────────────────────────────────────┘

✨ **Quick Access to Everything!**
                """,
                color=0x00ff88,
                timestamp=datetime.datetime.now()
            )

            embed3.add_field(
                name="🎂 Birthdays",
                value="```Set & celebrate```",
                inline=True
            )
            embed3.add_field(
                name="📊 Leveling",
                value="```XP & Progress```",
                inline=True
            )
            embed3.add_field(
                name="🏆 Leaderboard",
                value="```Top players```",
                inline=True
            )
            embed3.add_field(
                name="💎 Diamonds",
                value="```Check balance```",
                inline=True
            )

            embed3.set_footer(
                text="✨ Powered by PCRP | All-in-One Command Center",
                icon_url="https://cdn.discordapp.com/emojis/1234567890123456789.png"
            )
            embed3.set_thumbnail(url="https://img.icons8.com/color/96/000000/dashboard.png")

            view3 = AllFeaturesView()
            await general_channel.send(embed=embed3, view=view3)

            print(f"✅ Auto-setup all panels in {guild.name}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Level system
    async with aiosqlite.connect(bot.db_path) as db:
        # Get current user data
        async with db.execute(
            "SELECT xp, level FROM users WHERE user_id = ? AND guild_id = ?",
            (message.author.id, message.guild.id)
        ) as cursor:
            result = await cursor.fetchone()

        if result:
            xp, level = result
            new_xp = xp + random.randint(10, 25)
            new_level = new_xp // 100

            if new_level > level:
                # Level up!
                embed = discord.Embed(
                    title="🎉 Level Up!",
                    description=f"{message.author.mention} reached level {new_level}!",
                    color=0x00ff88
                )
                await message.channel.send(embed=embed)

            await db.execute(
                "UPDATE users SET xp = ?, level = ?, messages = messages + 1 WHERE user_id = ? AND guild_id = ?",
                (new_xp, new_level, message.author.id, message.guild.id)
            )
        else:
            # New user
            await db.execute(
                "INSERT INTO users (user_id, guild_id, xp, level, messages) VALUES (?, ?, ?, ?, ?)",
                (message.author.id, message.guild.id, 15, 0, 1)
            )

        await db.commit()

    # Log message
    async with aiosqlite.connect(bot.db_path) as db:
        await db.execute(
            "INSERT INTO logs (guild_id, log_type, user_id, channel_id, content) VALUES (?, ?, ?, ?, ?)",
            (message.guild.id, "message", message.author.id, message.channel.id, message.content[:500])
        )
        await db.commit()

    await bot.process_commands(message)

# Start the bot with token from environment variable
if __name__ == "__main__":
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("❌ DISCORD_BOT_TOKEN not found in environment variables!")
        print("Please set your Discord bot token in the Secrets tab.")
        exit(1)
    
    bot.run(token)
