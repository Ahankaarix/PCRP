
# 🤖 PCRP Discord Bot

A feature-rich Discord bot with leveling system, ticket support, birthday celebrations, and Diamond-based mini games.

## 📋 Table of Contents

- [Features](#-features)
- [Setup Instructions](#-setup-instructions)
- [Bot Configuration](#-bot-configuration)
- [Commands](#-commands)
- [Channel Configuration](#-channel-configuration)
- [Diamond System](#-diamond-system)
- [Database Structure](#-database-structure)
- [Development](#-development)

## ✨ Features

### 🎫 **Ticket System**
- Create private support tickets
- Automatic ticket management
- Staff-only access controls
- Auto-delete after closure

### 📈 **Leveling & XP System**
- Automatic XP gain from messages (15-25 XP per message)
- Level progression (100 XP per level)
- Visual level-up notifications
- Server leaderboards

### 🎂 **Birthday System**
- Set personal birthdays
- Automatic daily birthday notifications
- Optional age calculation
- Celebration messages in general chat

### 💎 **Diamond Mini Games** (Channel Restricted)
- **Conversion Rate**: 100 Diamonds = ₹1 (no decimals, rounded down)
- Free games with Diamond rewards
- Betting games with risk/reward
- Balance tracking system

### 🎉 **Giveaway System**
- Interactive giveaway creation
- Automatic winner selection
- Customizable duration and prizes

### 📊 **Logging & Analytics**
- User activity tracking
- Command usage statistics
- Database-backed persistence

## 🛠 Setup Instructions

### Prerequisites
- Python 3.11+
- Discord Bot Token
- Replit Account (recommended)

### 1. Create Discord Application
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create new application
3. Go to "Bot" section
4. Copy the bot token
5. Enable necessary intents:
   - Message Content Intent
   - Server Members Intent
   - Guilds Intent

### 2. Bot Permissions
Required bot permissions:
```
- Send Messages
- Use Slash Commands
- Manage Channels
- Manage Messages
- Read Message History
- Add Reactions
- Embed Links
```

### 3. Environment Setup
1. In Replit, go to Secrets tab
2. Add new secret:
   - **Key**: `DISCORD_BOT_TOKEN`
   - **Value**: Your Discord bot token

### 4. Channel Configuration
Update channel IDs in `main.py`:
```python
TICKET_CHANNEL_ID = YOUR_TICKET_CHANNEL_ID
GENERAL_CHANNEL_ID = YOUR_GENERAL_CHANNEL_ID
CONVERT_CHANNEL_ID = YOUR_CONVERT_CHANNEL_ID
DAILY_CHANNEL_ID = YOUR_DAILY_CHANNEL_ID
MINIGAMES_CHANNEL_ID = YOUR_MINIGAMES_CHANNEL_ID
POINTS_CHANNEL_ID = YOUR_POINTS_CHANNEL_ID
```

### 5. Run the Bot
```bash
python main.py
```

## ⚙️ Bot Configuration

### Required Channels
Create these channels in your Discord server:

| Channel Type | Purpose | Required Commands |
|--------------|---------|-------------------|
| 🎫 **Tickets** | Support ticket creation | Ticket panels |
| 💬 **General** | Main chat, birthdays | Level notifications |
| 💱 **Convert** | Currency conversion | `/convert_points`, `/convert_giftcard` |
| 🎁 **Daily** | Daily rewards | `/claim_daily` |
| 🎮 **Minigames** | Diamond games | `/coinflip`, `/dice`, `/tos_coin` |
| 💎 **Points** | Balance checking | `/get_points`, `/transfer_points` |

## 🎮 Commands

### Mini Game Commands (💎 Diamond Restricted)
> **Channel**: Only in designated minigames channel

#### `/coinflip <choice>`
- **Description**: Free coin toss game - guess Heads or Tails
- **Reward**: 100 Diamonds for correct guess
- **Cost**: Free to play
- **Example**: `/coinflip choice:Heads`

#### `/dice <guess>`
- **Description**: Guess the dice number (1-6)
- **Reward**: 100 Diamonds for exact match
- **Cost**: Free to play
- **Example**: `/dice guess:4`

#### `/tos_coin <choice> [bet]`
- **Description**: High-stakes betting game with double-or-nothing
- **Minimum Bet**: 100 Diamonds
- **Reward**: Double your bet if you win
- **Risk**: Lose your entire bet if wrong
- **Example**: `/tos_coin choice:Head bet:500`

#### `/diamond_balance`
- **Description**: Check your Diamond balance and Rupee conversion
- **Shows**: Current Diamonds, Rupee value (100 💎 = ₹1)

### Leveling Commands

#### `/level [member]`
- **Description**: Check level statistics
- **Shows**: Current level, XP progress, message count
- **Example**: `/level` or `/level member:@username`

#### `/leaderboard`
- **Description**: Display server's top 10 users by level
- **Shows**: Rankings with levels and XP

### Birthday Commands

#### `/birthday <date> [year]`
- **Description**: Set your birthday for automatic celebrations
- **Format**: MM-DD (e.g., 12-25)
- **Optional**: Birth year for age calculation
- **Example**: `/birthday date:12-25 year:1995`

### Utility Commands

#### `/giveaway <prize> <duration> [winners]`
- **Description**: Create interactive giveaways
- **Duration**: Minutes until giveaway ends
- **Winners**: Number of winners (default: 1)
- **Example**: `/giveaway prize:"Discord Nitro" duration:60 winners:2`

### Setup Commands

#### `/setup`
- **Description**: Initialize all bot features
- **Creates**: Ticket panels, welcome messages, feature buttons
- **Required**: Administrator permissions

#### `/ticket <channel>`
- **Description**: Set up ticket system in specific channel
- **Creates**: Ticket creation panel with button
- **Example**: `/ticket channel:#tickets`

## 💎 Diamond System

### Conversion Rate
- **100 Diamonds = ₹1**
- **No decimal places** (rounded down)
- **Example**: 850 Diamonds = ₹8

### Earning Methods
1. **Free Games**: 100 Diamonds per win
   - Coinflip (50% chance)
   - Dice (16.67% chance)

2. **Betting Games**: Risk/Reward based
   - ToS Coin: Double or nothing
   - Minimum bet: 100 Diamonds

### Usage Restrictions
- **Mini games only** - No Diamond integration with tickets or birthdays
- **Channel restricted** - Must use designated minigames channel
- **Balance tracking** - All transactions logged

## 📊 Database Structure

### Tables Overview

#### `users` - Leveling System
```sql
user_id INTEGER PRIMARY KEY
guild_id INTEGER
xp INTEGER DEFAULT 0
level INTEGER DEFAULT 0
messages INTEGER DEFAULT 0
```

#### `diamonds` - Mini Game Currency
```sql
user_id INTEGER PRIMARY KEY
guild_id INTEGER
balance INTEGER DEFAULT 0
last_daily TIMESTAMP
daily_streak INTEGER DEFAULT 0
total_earned INTEGER DEFAULT 0
multiplier REAL DEFAULT 1.0
```

#### `tickets` - Support System
```sql
ticket_id INTEGER PRIMARY KEY AUTOINCREMENT
user_id INTEGER
guild_id INTEGER
channel_id INTEGER
status TEXT DEFAULT 'open'
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```

#### `birthdays` - Celebration System
```sql
user_id INTEGER PRIMARY KEY
guild_id INTEGER
birth_date TEXT
birth_year INTEGER
```

#### `giveaways` - Event System
```sql
giveaway_id INTEGER PRIMARY KEY AUTOINCREMENT
guild_id INTEGER
channel_id INTEGER
message_id INTEGER
prize TEXT
winner_count INTEGER
end_time TIMESTAMP
host_id INTEGER
participants TEXT DEFAULT '[]'
```

## 🔧 Development

### File Structure
```
├── main.py              # Main bot file
├── bot_database.db      # SQLite database
├── pyproject.toml       # Dependencies
├── .replit             # Replit configuration
└── README.md           # This file
```

### Dependencies
```python
aiosqlite>=0.21.0    # Async SQLite database
discord-py>=2.5.2    # Discord API wrapper
pillow>=11.2.1       # Image processing
```

### Key Classes
- `DiscordBot`: Main bot class with database setup
- `TicketView`: Ticket creation interface
- `AllFeaturesView`: Multi-purpose feature buttons
- `GiveawayView`: Giveaway participation interface
- `BirthdayModal`: Birthday input form

### Event Handlers
- `on_ready`: Bot startup and command sync
- `on_message`: XP gain and level progression
- `birthday_check`: Daily birthday notifications (24h loop)

## 🚀 Deployment

### Replit Deployment (Recommended)
1. Fork this repository to Replit
2. Set up Discord bot token in Secrets
3. Configure channel IDs
4. Click "Run" button

### Keep-Alive Features
- Automatic database creation
- Command synchronization
- Error handling and logging
- Persistent bot connection

## 📞 Support

### Common Issues

**Bot not responding to commands:**
- Check bot permissions
- Verify slash commands are synced
- Ensure bot token is correct

**Channel restrictions not working:**
- Verify channel IDs in configuration
- Check bot has access to channels
- Confirm slash command registration

**Database errors:**
- Bot automatically creates database on startup
- Check file permissions in environment

### Feature Requests
- Create GitHub issues for new features
- Join our Discord server for support
- Check existing commands with `/help`

---

## 📝 License

This project is open source and available under the MIT License.

---

**Made with ❤️ for PCRP Community**

*Last updated: December 2024*
