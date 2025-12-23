# Roblox Monitor Discord Bot

A Discord bot that monitors Roblox user activity and creates dedicated channels for each monitored user. Get real-time notifications about friends, followers, game activity, and more!

## ✨ Features

- **Discord Bot Control**: Control monitoring through Discord slash commands
- **Automatic Channel Creation**: Creates a dedicated channel for each monitored user
- **Friends Tracking**: Monitors friend additions and removals with usernames
- **Followers Count**: Tracks follower count changes with +/- differences
- **Online Status**: Detects when users go online/offline or enter Roblox Studio
- **Game Activity**: Monitors what game the user is playing and detects game switches
- **Game History**: Tracks and displays game history in a local database
- **User Profiles**: View user bio, join date, connections, and communities
- **Communities**: View all groups/communities a user is in, sorted by member count
- **Multi-User Support**: Monitor multiple users simultaneously

## 📋 Requirements

- Python 3.8+
- Discord Bot Token
- `discord.py` library
- `requests` library

## 🚀 Installation

1. Clone this repository:
```bash
git clone https://github.com/Jahbas/roblox-stalker.git
cd roblox-stalker
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a Discord Bot:
   - Go to https://discord.com/developers/applications
   - Create a new application
   - Go to "Bot" section and create a bot
   - Copy the bot token
   - Enable "Message Content Intent" and "Server Members Intent" in Privileged Gateway Intents

4. Invite the bot to your server:
   - Go to OAuth2 → URL Generator
   - Select "bot" and "applications.commands" scopes
   - Select "Administrator" permissions (or specific permissions: Manage Channels, Send Messages, Embed Links)
   - Copy the generated URL and open it in your browser
   - Select your server and authorize

5. Configure the bot:
   - Copy `config.py.example` to `config.py` (or create `config.py` from the example)
   - Open `config.py`
   - Set `DISCORD_BOT_TOKEN` to your bot token
   - Optionally set `GUILD_ID` to a specific server ID (or leave as None to use the first server)
   - Adjust `MONITORING_CATEGORY_NAME` if desired (default: "Roblox Monitoring")
   - Set `CHECK_INTERVAL` for monitoring frequency (default: 60 seconds)

## 🎯 Usage

### Starting the Bot

Run the bot:
```bash
python main.py
```

The bot will:
- Log in to Discord
- Initialize the database
- Sync slash commands
- Start monitoring any previously added users

### Discord Commands

All commands are slash commands (type `/` in Discord):

- `/adduser <roblox_id>` - Add a Roblox user to monitor and create a channel
- `/removeuser <roblox_id>` - Remove a user from monitoring
- `/listusers` - List all currently monitored users
- `/userinfo <roblox_id>` - Get detailed information about a user
- `/communities <roblox_id>` - View all communities/groups for a user
- `/gamehistory <roblox_id> [limit]` - View game history (default: 25 games)
- `/debugpresence <roblox_id>` - Debug presence data for a user
- `/sync` - Manually sync slash commands
- `/startmonitoring` - Start monitoring all users
- `/stopmonitoring` - Stop monitoring

### Example Workflow

1. Add a user to monitor:
   ```
   /adduser 1151641799
   ```
   This will:
   - Create a channel for the user
   - Send initial profile information
   - Start tracking their activity

2. View user information:
   ```
   /userinfo 1151641799
   ```

3. View communities:
   ```
   /communities 1151641799
   ```

4. View game history:
   ```
   /gamehistory 1151641799 50
   ```

5. List all monitored users:
   ```
   /listusers
   ```

## 📊 Channel Structure

When you add a user, the bot creates:
- A category: "Roblox Monitoring" (or your custom name)
- A channel: `{username}-{user_id}` (e.g., `sologamer1919-1151641799`)

All activity notifications for that user will be sent to their dedicated channel.

## 🗄️ Database

The bot uses a local SQLite database (`roblox_monitor.db`) to store:
- Game history
- User information
- Channel mappings
- Monitoring status

Data persists between bot restarts.

## ⚙️ Configuration Options

In `config.py`:

- `DISCORD_BOT_TOKEN`: Your Discord bot token (required)
- `GUILD_ID`: Specific server ID (None = use first server)
- `MONITORING_CATEGORY_NAME`: Category name for channels
- `CHECK_INTERVAL`: Seconds between checks (default: 60)
- `DETAILED_FRIENDS_TRACKING`: Track individual friends (True) or just count (False)
- `COMMAND_PREFIX`: Prefix for text commands (default: "!")

## 🔒 Permissions Required

The bot needs the following permissions:
- **Manage Channels**: To create channels and categories
- **Send Messages**: To send notifications
- **Embed Links**: To send rich embeds
- **Read Message History**: To read commands

## 📝 Notes

- The bot automatically starts monitoring when users are added
- Channels are created automatically but not deleted when users are removed (you can manually delete them)
- Game history is stored permanently in the database
- Monitoring continues even after bot restarts (if users are in database)

## 🛠️ Troubleshooting

**Bot doesn't respond to commands:**
- Make sure the bot has the "applications.commands" scope
- Wait a few minutes after inviting for commands to sync
- Try using `/sync` command or restarting the bot

**Can't create channels:**
- Check bot permissions in server settings
- Ensure bot role is above the category in hierarchy

**Monitoring not working:**
- Use `/startmonitoring` command
- Check if users are added with `/listusers`
- Verify CHECK_INTERVAL is not too low (may hit rate limits)

**Game detection not working:**
- Use `/debugpresence <roblox_id>` to see what the API returns
- Check if the user is actually in a game (status should be "In Game")
- Verify the Roblox API is returning universeId or placeId

## 📄 License

MIT License - See LICENSE file for details.

## 🙏 Credits

Original concept by https://github.com/vmmie
