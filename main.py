
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

    await interaction.response.send_message("✅ Bot setup complete! All features are now active.", ephemeral=True)

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
