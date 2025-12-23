import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
from datetime import datetime, UTC
import requests
from config import (
    DISCORD_BOT_TOKEN,
    GUILD_ID,
    MONITORING_CATEGORY_NAME,
    CHECK_INTERVAL,
    DETAILED_FRIENDS_TRACKING
)

DB_FILE = "roblox_monitor.db"

def init_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            game_name TEXT NOT NULL,
            universe_id TEXT,
            place_id TEXT,
            started_at TIMESTAMP NOT NULL,
            ended_at TIMESTAMP,
            duration_seconds INTEGER,
            UNIQUE(user_id, universe_id, started_at)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_info (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            display_name TEXT,
            last_updated TIMESTAMP NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monitored_users (
            roblox_user_id TEXT PRIMARY KEY,
            roblox_username TEXT NOT NULL,
            discord_channel_id TEXT NOT NULL,
            guild_id TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            added_at TIMESTAMP NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_game_history_user_time 
        ON game_history(user_id, started_at DESC)
    ''')
    conn.commit()
    conn.close()
    print(f"✓ Database initialized: {DB_FILE}")

def store_game_session(user_id, username, game_name, universe_id=None, place_id=None, started_at=None):
    if started_at is None:
        started_at = datetime.now(UTC)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO game_history 
            (user_id, username, game_name, universe_id, place_id, started_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (str(user_id), username, game_name, str(universe_id) if universe_id else None, 
              str(place_id) if place_id else None, started_at.isoformat()))
        conn.commit()
    except Exception as e:
        print(f"Error storing game session: {e}")
    finally:
        conn.close()

def update_user_info(user_id, username, display_name=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO user_info 
            (user_id, username, display_name, last_updated)
            VALUES (?, ?, ?, ?)
        ''', (str(user_id), username, display_name, datetime.now(UTC).isoformat()))
        conn.commit()
    except Exception as e:
        print(f"Error updating user info: {e}")
    finally:
        conn.close()

def get_game_history(user_id, limit=25):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT game_name, universe_id, place_id, started_at, ended_at, duration_seconds
            FROM game_history
            WHERE user_id = ?
            ORDER BY started_at DESC
            LIMIT ?
        ''', (str(user_id), limit))
        return cursor.fetchall()
    except Exception as e:
        print(f"Error fetching game history: {e}")
        return []
    finally:
        conn.close()

def get_unique_games(user_id, limit=25):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT game_name, COUNT(*) as play_count, MAX(started_at) as last_played
            FROM game_history
            WHERE user_id = ?
            GROUP BY game_name
            ORDER BY last_played DESC
            LIMIT ?
        ''', (str(user_id), limit))
        return cursor.fetchall()
    except Exception as e:
        print(f"Error fetching unique games: {e}")
        return []
    finally:
        conn.close()

def get_user_info(user_id):
    try:
        response = requests.get(f"https://users.roblox.com/v1/users/{user_id}")
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print(f"Error fetching user info: {e}")
        return None

def get_user_bio(user_id):
    try:
        response = requests.get(f"https://users.roblox.com/v1/users/{user_id}")
        if response.status_code == 200:
            data = response.json()
            return data.get("description", "")
        return None
    except Exception as e:
        print(f"Error fetching user bio: {e}")
        return None

def get_user_join_date(user_id):
    try:
        response = requests.get(f"https://users.roblox.com/v1/users/{user_id}")
        if response.status_code == 200:
            data = response.json()
            created = data.get("created")
            if created:
                return datetime.fromisoformat(created.replace('Z', '+00:00'))
        return None
    except Exception as e:
        print(f"Error fetching join date: {e}")
        return None

def get_user_connections(user_id):
    try:
        response = requests.get(f"https://users.roblox.com/v1/users/{user_id}")
        if response.status_code == 200:
            data = response.json()
            return data.get("socialLinks", []) or []
        return []
    except Exception as e:
        print(f"Error fetching connections: {e}")
        return []

def get_user_groups(user_id):
    try:
        response = requests.get(f"https://groups.roblox.com/v2/users/{user_id}/groups/roles")
        if response.status_code == 200:
            data = response.json()
            groups = []
            for item in data.get("data", []):
                group = item.get("group", {})
                role = item.get("role", {})
                groups.append({
                    "id": group.get("id"),
                    "name": group.get("name"),
                    "member_count": group.get("memberCount", 0),
                    "role": role.get("name", "Member"),
                    "rank": role.get("rank", 0),
                    "is_owner": role.get("rank", 0) >= 255,
                    "joined_at": None
                })
            return groups
        return []
    except Exception as e:
        print(f"Error fetching user groups: {e}")
        return []

def get_user_presence(user_id):
    try:
        payload = {"userIds": [user_id]}
        response = requests.post("https://presence.roblox.com/v1/presence/users", json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get("userPresences"):
                return data["userPresences"][0]
        return None
    except Exception as e:
        print(f"Error fetching user presence: {e}")
        return None

def get_friends_list(user_id):
    try:
        friends = {}
        url = f"https://friends.roblox.com/v1/users/{user_id}/friends"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            for friend in data.get("data", []):
                friend_id = friend.get("id")
                friend_name = friend.get("name") or friend.get("username") or f"User_{friend_id}"
                if friend_id:
                    friends[friend_id] = friend_name
            return friends
        else:
            print(f"Friends API returned status {response.status_code}")
            return None
    except Exception as e:
        print(f"Error fetching friends list: {e}")
        return None

def get_friends_count(user_id):
    try:
        response = requests.get(f"https://friends.roblox.com/v1/users/{user_id}/friends/count")
        if response.status_code == 200:
            return response.json().get("count", 0)
        return None
    except Exception as e:
        print(f"Error fetching friends count: {e}")
        return None

def get_followers_count(user_id):
    try:
        response = requests.get(f"https://friends.roblox.com/v1/users/{user_id}/followers/count")
        if response.status_code == 200:
            return response.json().get("count", 0)
        return None
    except Exception as e:
        print(f"Error fetching followers count: {e}")
        return None

def get_game_details(place_id):
    try:
        response = requests.get(f"https://games.roblox.com/v1/games/multiget-place-details?placeIds={place_id}")
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                game_data = data[0]
                game_name = game_data.get("name") or game_data.get("placeName") or "Unknown Game"
                return game_name
        return None
    except Exception as e:
        print(f"Error fetching game details: {e}")
        return None

def get_game_name_from_universe(universe_id):
    try:
        response = requests.get(f"https://games.roblox.com/v1/games?universeIds={universe_id}")
        if response.status_code == 200:
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                return data["data"][0].get("name", "Unknown Game")
        return None
    except Exception as e:
        print(f"Error fetching game name from universe: {e}")
        return None

def get_game_info_from_presence(presence):
    if not presence:
        return None
    game_info = {
        "universe_id": presence.get("universeId"),
        "place_id": presence.get("placeId") or presence.get("rootPlaceId"),
        "game_name": None
    }
    if game_info["universe_id"]:
        game_name = get_game_name_from_universe(game_info["universe_id"])
        if game_name:
            game_info["game_name"] = game_name
            return game_info
    if game_info["place_id"] and not game_info["game_name"]:
        game_name = get_game_details(game_info["place_id"])
        if game_name:
            game_info["game_name"] = game_name
            return game_info
    return game_info if game_info["universe_id"] or game_info["place_id"] else None

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_messages = True

bot = commands.Bot(command_prefix='!', intents=intents)

monitoring_active = False
user_states = {}

def get_monitored_users():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT roblox_user_id, roblox_username, discord_channel_id, guild_id
            FROM monitored_users
            WHERE is_active = 1
        ''')
        return cursor.fetchall()
    finally:
        conn.close()

def add_monitored_user(roblox_user_id, roblox_username, discord_channel_id, guild_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO monitored_users
            (roblox_user_id, roblox_username, discord_channel_id, guild_id, is_active, added_at)
            VALUES (?, ?, ?, ?, 1, ?)
        ''', (str(roblox_user_id), roblox_username, str(discord_channel_id), str(guild_id), datetime.now(UTC).isoformat()))
        conn.commit()
    finally:
        conn.close()

def remove_monitored_user(roblox_user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE monitored_users
            SET is_active = 0
            WHERE roblox_user_id = ?
        ''', (str(roblox_user_id),))
        conn.commit()
    finally:
        conn.close()

def get_channel_for_user(roblox_user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT discord_channel_id, guild_id
            FROM monitored_users
            WHERE roblox_user_id = ? AND is_active = 1
        ''', (str(roblox_user_id),))
        result = cursor.fetchone()
        return result if result else None
    finally:
        conn.close()

def create_activity_embed(message, color=3447003):
    embed = discord.Embed(
        title="Activity Update",
        description=message,
        color=color,
        timestamp=datetime.now(UTC)
    )
    embed.set_footer(text="Roblox Monitor • Real-time Tracking", icon_url="https://www.roblox.com/favicon.ico")
    embed.set_author(name="Roblox Activity Monitor", icon_url="https://www.roblox.com/favicon.ico")
    return embed

def create_startup_embed(username, user_id, friends_count, followers_count, presence, bio=None, join_date=None, connections=None):
    status_map = {0: "Offline", 1: "Online", 2: "In Game", 3: "In Studio"}
    status_code = presence.get("userPresenceType", 0) if presence else 0
    current_status = status_map.get(status_code, "Unknown")
    game_info = "Not playing"
    if presence and status_code == 2:
        universe_id = presence.get("universeId")
        place_id = presence.get("placeId") or presence.get("rootPlaceId")
        if universe_id or place_id:
            game_data = get_game_info_from_presence(presence)
            if game_data and game_data.get("game_name"):
                game_info = game_data["game_name"]
            else:
                if universe_id:
                    game_name = get_game_name_from_universe(universe_id)
                    if game_name:
                        game_info = game_name
                if game_info == "Not playing" and place_id:
                    game_name = get_game_details(place_id)
                    if game_name:
                        game_info = game_name
                if game_info == "Not playing":
                    game_info = "Unknown Game"
    bio_display = bio[:200] + "..." if bio and len(bio) > 200 else (bio if bio else "No bio set")
    join_date_formatted = join_date.strftime("%B %d, %Y") if join_date else "Unable to fetch"
    connections_display = "None"
    if connections and len(connections) > 0:
        conn_list = []
        for conn in connections[:5]:
            conn_type = conn.get("type", "Unknown")
            conn_url = conn.get("url", "")
            if conn_url:
                conn_list.append(f"[{conn_type}]({conn_url})")
        else:
                conn_list.append(conn_type)
        connections_display = ", ".join(conn_list) if conn_list else "None"
    friends_display = f"{friends_count:,}" if friends_count is not None else "Unable to fetch"
    followers_display = f"{followers_count:,}" if followers_count is not None else "Unable to fetch"
    profile_url = f"https://www.roblox.com/users/{user_id}/profile"
    embed = discord.Embed(
        title="Monitor Initialized",
        description=f"Successfully started monitoring [**{username}**]({profile_url})",
        color=5763719,
        timestamp=datetime.now(UTC)
    )
    embed.add_field(
        name="Statistics",
        value=f"**Friends:** {friends_display}\n**Followers:** {followers_display}\n**Join Date:** {join_date_formatted}",
        inline=False
    )
    if bio:
        embed.add_field(
            name="Bio",
            value=bio_display[:1024],
            inline=False
        )
    if connections_display != "None":
        embed.add_field(
            name="Connections",
            value=connections_display,
            inline=False
        )
    embed.add_field(name="Current Status", value=current_status, inline=True)
    embed.add_field(name="Current Game", value=game_info, inline=True)
    embed.add_field(
        name="Monitor Settings",
        value=f"**Check Interval:** {CHECK_INTERVAL}s\n**Tracking Mode:** {'Detailed' if DETAILED_FRIENDS_TRACKING else 'Count Only'}",
        inline=True
    )
    embed.set_footer(text="Roblox Monitor • Real-time Activity Tracking", icon_url="https://www.roblox.com/favicon.ico")
    embed.set_author(
        name=username,
        url=profile_url,
        icon_url=f"https://www.roblox.com/headshot-thumbnail/image?userId={user_id}&width=420&height=420&format=png"
    )
    embed.set_thumbnail(url=f"https://www.roblox.com/headshot-thumbnail/image?userId={user_id}&width=420&height=420&format=png")
    return embed

@bot.event
async def on_ready():
    print(f'{bot.user} has logged in!')
    print(f'Bot is in {len(bot.guilds)} guild(s)')
    init_database()
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
        for cmd in synced:
            print(f'  - {cmd.name}')
    except Exception as e:
        print(f'Failed to sync commands: {e}')
        import traceback
        traceback.print_exc()
    monitored = get_monitored_users()
    if monitored:
        print(f'Found {len(monitored)} monitored user(s), starting monitoring...')
        await start_monitoring()

@bot.tree.command(name="sync", description="Sync slash commands")
async def sync(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        synced = await bot.tree.sync()
        await interaction.followup.send(f'✅ Synced {len(synced)} command(s)')
    except Exception as e:
        await interaction.followup.send(f'❌ Failed to sync: {e}')

@tasks.loop(seconds=CHECK_INTERVAL)
async def monitoring_loop():
    if not monitoring_active:
        return
    monitored_users = get_monitored_users()
    for roblox_user_id, roblox_username, discord_channel_id, guild_id in monitored_users:
        try:
            guild = bot.get_guild(int(guild_id))
            if not guild:
                continue
            channel = guild.get_channel(int(discord_channel_id))
            if not channel:
                continue
            user_id = str(roblox_user_id)
            if user_id not in user_states:
                user_states[user_id] = {
                    "friends_dict": {},
                    "friends_count": None,
                    "followers_count": None,
                    "online_status": None,
                    "game_universe_id": None,
                    "game_place_id": None,
                    "game_name": None,
                    "game_start_time": None
                }
            previous_state = user_states[user_id]
            if DETAILED_FRIENDS_TRACKING:
                current_friends_dict = get_friends_list(user_id)
                if current_friends_dict is not None and previous_state["friends_dict"]:
                    previous_ids = set(previous_state["friends_dict"].keys())
                    current_ids = set(current_friends_dict.keys())
                    added_ids = current_ids - previous_ids
                    if added_ids:
                        added_names = [current_friends_dict[fid] for fid in added_ids]
                        message = f"**{roblox_username}** added a new friend: **{added_names[0]}**" if len(added_names) == 1 else f"**{roblox_username}** added {len(added_names)} new friends"
                        await channel.send(embed=create_activity_embed(message))
                    removed_ids = previous_ids - current_ids
                    if removed_ids:
                        removed_names = [previous_state["friends_dict"][fid] for fid in removed_ids]
                        message = f"**{roblox_username}** removed a friend: **{removed_names[0]}**" if len(removed_names) == 1 else f"**{roblox_username}** removed {len(removed_names)} friends"
                        await channel.send(embed=create_activity_embed(message))
                    if added_ids or removed_ids:
                        previous_state["friends_dict"] = current_friends_dict
            current_followers = get_followers_count(user_id)
            if current_followers is not None and previous_state["followers_count"] is not None:
                if current_followers != previous_state["followers_count"]:
                    diff = current_followers - previous_state["followers_count"]
                    change = f"+{diff}" if diff > 0 else str(diff)
                    message = f"**{roblox_username}** followers count changed: {previous_state['followers_count']} → {current_followers} ({change})"
                    await channel.send(embed=create_activity_embed(message))
                    previous_state["followers_count"] = current_followers
            current_presence = get_user_presence(user_id)
            if current_presence:
                current_status = current_presence.get("userPresenceType", 0)
                current_game_universe_id = current_presence.get("universeId")
                current_game_place_id = current_presence.get("placeId") or current_presence.get("rootPlaceId")
                current_game_name = None
                
                if current_status == 2:
                    if current_game_universe_id or current_game_place_id:
                        if current_game_universe_id:
                            current_game_name = get_game_name_from_universe(current_game_universe_id)
                        if not current_game_name and current_game_place_id:
                            current_game_name = get_game_details(current_game_place_id)
                        if not current_game_name:
                            current_game_name = "Unknown Game"
                    
                    prev_has_game = previous_state["game_universe_id"] is not None or previous_state["game_place_id"] is not None
                    curr_has_game = current_game_universe_id is not None or current_game_place_id is not None
                    
                    game_changed = False
                    if not prev_has_game and curr_has_game:
                        game_changed = True
                    elif prev_has_game and curr_has_game:
                        if current_game_universe_id != previous_state["game_universe_id"]:
                            game_changed = True
                        elif current_game_place_id and current_game_place_id != previous_state["game_place_id"]:
                            game_changed = True
                    elif prev_has_game and not curr_has_game:
                        game_changed = True
                    
                    if game_changed:
                        if prev_has_game:
                            message = f"**{roblox_username}** stopped playing: {previous_state['game_name'] or 'Unknown Game'}"
                            await channel.send(embed=create_activity_embed(message))
                        if curr_has_game:
                            game_name = current_game_name or "Unknown Game"
                            if prev_has_game:
                                message = f"**{roblox_username}** switched games: {previous_state['game_name'] or 'Unknown Game'} → {game_name}"
                            else:
                                message = f"**{roblox_username}** started playing: {game_name}"
                            await channel.send(embed=create_activity_embed(message))
                            store_game_session(user_id, roblox_username, game_name, 
                                             current_game_universe_id, current_game_place_id)
                            previous_state["game_name"] = game_name
                            previous_state["game_start_time"] = datetime.now(UTC)
                        else:
                            previous_state["game_name"] = None
                            previous_state["game_start_time"] = None
                        previous_state["game_universe_id"] = current_game_universe_id
                        previous_state["game_place_id"] = current_game_place_id
                    elif not prev_has_game and curr_has_game:
                        previous_state["game_universe_id"] = current_game_universe_id
                        previous_state["game_place_id"] = current_game_place_id
                        previous_state["game_name"] = current_game_name or "Unknown Game"
                        previous_state["game_start_time"] = datetime.now(UTC)
                else:
                    if previous_state["game_universe_id"] is not None or previous_state["game_place_id"] is not None:
                        message = f"**{roblox_username}** stopped playing: {previous_state['game_name'] or 'Unknown Game'}"
                        await channel.send(embed=create_activity_embed(message))
                        previous_state["game_universe_id"] = None
                        previous_state["game_place_id"] = None
                        previous_state["game_name"] = None
                        previous_state["game_start_time"] = None
                
                previous_state["online_status"] = current_status
            else:
                if previous_state["game_universe_id"] is not None or previous_state["game_place_id"] is not None:
                    message = f"**{roblox_username}** stopped playing: {previous_state['game_name'] or 'Unknown Game'}"
                    await channel.send(embed=create_activity_embed(message))
                    previous_state["game_universe_id"] = None
                    previous_state["game_place_id"] = None
                    previous_state["game_name"] = None
                    previous_state["game_start_time"] = None
                previous_state["online_status"] = None
        except Exception as e:
            print(f"Error monitoring user {roblox_user_id}: {e}")

async def start_monitoring():
    global monitoring_active
    monitored_users = get_monitored_users()
    if not monitored_users:
        return
    monitoring_active = True
    for roblox_user_id, roblox_username, discord_channel_id, guild_id in monitored_users:
        user_id = str(roblox_user_id)
        guild = bot.get_guild(int(guild_id))
        if not guild:
            continue
        channel = guild.get_channel(int(discord_channel_id))
        if not channel:
            continue
        user_info = get_user_info(user_id)
        if user_info:
            username = user_info.get("name", roblox_username)
            update_user_info(user_id, username, user_info.get("displayName"))
            if DETAILED_FRIENDS_TRACKING:
                friends_dict = get_friends_list(user_id)
                if friends_dict is not None:
                    user_states[user_id] = {"friends_dict": friends_dict}
                else:
                    user_states[user_id] = {"friends_dict": {}}
            else:
                user_states[user_id] = {"friends_dict": {}}
            user_states[user_id]["friends_count"] = get_friends_count(user_id)
            user_states[user_id]["followers_count"] = get_followers_count(user_id)
            presence = get_user_presence(user_id)
            if presence:
                current_status = presence.get("userPresenceType", 0)
                user_states[user_id]["online_status"] = current_status
                if current_status == 2:
                    universe_id = presence.get("universeId")
                    place_id = presence.get("placeId") or presence.get("rootPlaceId")
                    if universe_id or place_id:
                        game_name = None
                        if universe_id:
                            game_name = get_game_name_from_universe(universe_id)
                        if not game_name and place_id:
                            game_name = get_game_details(place_id)
                        user_states[user_id]["game_universe_id"] = universe_id
                        user_states[user_id]["game_place_id"] = place_id
                        user_states[user_id]["game_name"] = game_name or "Unknown Game"
                        user_states[user_id]["game_start_time"] = datetime.now(UTC)
                    else:
                        user_states[user_id]["game_universe_id"] = None
                        user_states[user_id]["game_place_id"] = None
                        user_states[user_id]["game_name"] = None
                        user_states[user_id]["game_start_time"] = None
                else:
                    user_states[user_id]["game_universe_id"] = None
                    user_states[user_id]["game_place_id"] = None
                    user_states[user_id]["game_name"] = None
                    user_states[user_id]["game_start_time"] = None
            else:
                user_states[user_id]["online_status"] = None
                user_states[user_id]["game_universe_id"] = None
                user_states[user_id]["game_place_id"] = None
                user_states[user_id]["game_name"] = None
                user_states[user_id]["game_start_time"] = None
            bio = get_user_bio(user_id)
            join_date = get_user_join_date(user_id)
            connections = get_user_connections(user_id)
            embed = create_startup_embed(username, user_id, 
                                       user_states[user_id]["friends_count"],
                                       user_states[user_id]["followers_count"],
                                       presence, bio, join_date, connections)
            await channel.send(embed=embed)
    if not monitoring_loop.is_running():
        monitoring_loop.start()

async def stop_monitoring():
    global monitoring_active
    monitoring_active = False
    if monitoring_loop.is_running():
        monitoring_loop.stop()

async def send_communities_embed(channel, username, user_id):
    groups = get_user_groups(user_id)
    if not groups:
        embed = discord.Embed(
            title=f"Communities for {username}",
            description="No communities found",
            color=3447003,
            timestamp=datetime.now(UTC)
        )
        await channel.send(embed=embed)
        return
    groups_sorted = sorted(groups, key=lambda x: (not x["is_owner"], -x["member_count"]))
    owner_groups = [g for g in groups_sorted if g["is_owner"]]
    member_groups = [g for g in groups_sorted if not g["is_owner"]]
    profile_url = f"https://www.roblox.com/users/{user_id}/profile"
    embed = discord.Embed(
        title=f"Communities for {username}",
        description=f"**Total Communities:** {len(groups)}\n**Owned:** {len(owner_groups)}\n**Member:** {len(member_groups)}\n[View Profile]({profile_url})",
        color=3447003,
        timestamp=datetime.now(UTC)
    )
    if owner_groups:
        owner_text = []
        for group in owner_groups[:10]:
            group_url = f"https://www.roblox.com/groups/{group['id']}"
            member_count = f"{group['member_count']:,}" if group['member_count'] else "Unknown"
            owner_text.append(f"**[{group['name']}]({group_url})** (Owner)\nMembers: {member_count}")
        embed.add_field(
            name="Owned Communities",
            value="\n\n".join(owner_text),
            inline=False
        )
    if member_groups:
        member_text = []
        for group in member_groups[:15]:
            group_url = f"https://www.roblox.com/groups/{group['id']}"
            member_count = f"{group['member_count']:,}" if group['member_count'] else "Unknown"
            role = group.get('role', 'Member')
            member_text.append(f"**[{group['name']}]({group_url})** ({role})\nMembers: {member_count}")
        chunk_size = 10
        for i in range(0, len(member_text), chunk_size):
            chunk = member_text[i:i + chunk_size]
            embed.add_field(
                name=f"Communities ({i+1}-{min(i+chunk_size, len(member_text))})",
                value="\n\n".join(chunk),
                inline=False
            )
    embed.set_footer(text="Roblox Monitor • Sorted by member count", icon_url="https://www.roblox.com/favicon.ico")
    embed.set_author(
        name=username,
        url=profile_url,
        icon_url=f"https://www.roblox.com/headshot-thumbnail/image?userId={user_id}&width=420&height=420&format=png"
    )
    await channel.send(embed=embed)

@bot.tree.command(name="adduser", description="Add a Roblox user to monitor")
@app_commands.describe(roblox_id="The Roblox user ID to monitor")
async def adduser(interaction: discord.Interaction, roblox_id: str):
    await interaction.response.defer()
    try:
        int(roblox_id)
    except ValueError:
        await interaction.followup.send("❌ Invalid Roblox user ID. Please provide a numeric ID.")
        return
    user_info = get_user_info(roblox_id)
    if not user_info:
        await interaction.followup.send(f"❌ Could not find Roblox user with ID: {roblox_id}")
        return
    username = user_info.get("name", "Unknown")
    guild = interaction.guild
    category = discord.utils.get(guild.categories, name=MONITORING_CATEGORY_NAME)
    if not category:
        try:
            category = await guild.create_category(MONITORING_CATEGORY_NAME)
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to create categories.")
            return
    channel_name = f"{username.lower().replace(' ', '-')}-{roblox_id}"
    try:
        channel = await guild.create_text_channel(
            channel_name,
            category=category,
            topic=f"Monitoring {username} (ID: {roblox_id})"
        )
    except discord.Forbidden:
        await interaction.followup.send("❌ I don't have permission to create channels.")
        return
    add_monitored_user(roblox_id, username, channel.id, guild.id)
    update_user_info(roblox_id, username, user_info.get("displayName"))
    embed = discord.Embed(
        title="User Added to Monitoring",
        description=f"**{username}** (ID: {roblox_id}) has been added to monitoring.\nChannel: {channel.mention}",
        color=5763719,
        timestamp=datetime.now(UTC)
    )
    await interaction.followup.send(embed=embed)
    friends_count = get_friends_count(roblox_id)
    followers_count = get_followers_count(roblox_id)
    presence = get_user_presence(roblox_id)
    bio = get_user_bio(roblox_id)
    join_date = get_user_join_date(roblox_id)
    connections = get_user_connections(roblox_id)
    startup_embed = create_startup_embed(username, roblox_id, friends_count, followers_count, presence, bio, join_date, connections)
    await channel.send(embed=startup_embed)
    if not monitoring_active:
        await start_monitoring()

@bot.tree.command(name="removeuser", description="Remove a Roblox user from monitoring")
@app_commands.describe(roblox_id="The Roblox user ID to remove")
async def removeuser(interaction: discord.Interaction, roblox_id: str):
    await interaction.response.defer()
    channel_info = get_channel_for_user(roblox_id)
    if not channel_info:
        await interaction.followup.send(f"❌ User {roblox_id} is not being monitored.")
        return
    discord_channel_id, guild_id = channel_info
    remove_monitored_user(roblox_id)
    embed = discord.Embed(
        title="User Removed from Monitoring",
        description=f"User {roblox_id} has been removed from monitoring.",
        color=15158332,
        timestamp=datetime.now(UTC)
    )
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="listusers", description="List all monitored users")
async def listusers(interaction: discord.Interaction):
    await interaction.response.defer()
    monitored_users = get_monitored_users()
    if not monitored_users:
        await interaction.followup.send("No users are currently being monitored.")
        return
    embed = discord.Embed(
        title="Monitored Users",
        description=f"Currently monitoring {len(monitored_users)} user(s):",
        color=3447003,
        timestamp=datetime.now(UTC)
    )
    for roblox_user_id, roblox_username, discord_channel_id, guild_id in monitored_users:
        guild = bot.get_guild(int(guild_id))
        channel = guild.get_channel(int(discord_channel_id)) if guild else None
        channel_mention = channel.mention if channel else "Channel not found"
        embed.add_field(
            name=f"{roblox_username}",
            value=f"ID: {roblox_user_id}\nChannel: {channel_mention}",
            inline=True
        )
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="userinfo", description="Get information about a Roblox user")
@app_commands.describe(roblox_id="The Roblox user ID")
async def userinfo(interaction: discord.Interaction, roblox_id: str):
    await interaction.response.defer()
    user_info = get_user_info(roblox_id)
    if not user_info:
        await interaction.followup.send(f"❌ Could not find Roblox user with ID: {roblox_id}")
        return
    username = user_info.get("name", "Unknown")
    friends_count = get_friends_count(roblox_id)
    followers_count = get_followers_count(roblox_id)
    presence = get_user_presence(roblox_id)
    bio = get_user_bio(roblox_id)
    join_date = get_user_join_date(roblox_id)
    connections = get_user_connections(roblox_id)
    embed = create_startup_embed(username, roblox_id, friends_count, followers_count, presence, bio, join_date, connections)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="communities", description="Get communities for a Roblox user")
@app_commands.describe(roblox_id="The Roblox user ID")
async def communities(interaction: discord.Interaction, roblox_id: str):
    await interaction.response.defer()
    user_info = get_user_info(roblox_id)
    if not user_info:
        await interaction.followup.send(f"❌ Could not find Roblox user with ID: {roblox_id}")
        return
    username = user_info.get("name", "Unknown")
    await send_communities_embed(interaction.channel, username, roblox_id)
    await interaction.followup.send("Communities information sent!")

@bot.tree.command(name="startmonitoring", description="Start monitoring all users")
async def startmonitoring(interaction: discord.Interaction):
    await interaction.response.defer()
    if monitoring_active:
        await interaction.followup.send("⚠️ Monitoring is already active.")
        return
    await start_monitoring()
    await interaction.followup.send("✅ Monitoring started!")

@bot.tree.command(name="stopmonitoring", description="Stop monitoring")
async def stopmonitoring(interaction: discord.Interaction):
    await interaction.response.defer()
    if not monitoring_active:
        await interaction.followup.send("⚠️ Monitoring is not active.")
        return
    await stop_monitoring()
    await interaction.followup.send("⏹️ Monitoring stopped!")

@bot.tree.command(name="debugpresence", description="Debug presence data for a user")
@app_commands.describe(roblox_id="The Roblox user ID")
async def debugpresence(interaction: discord.Interaction, roblox_id: str):
    await interaction.response.defer()
    presence = get_user_presence(roblox_id)
    if not presence:
        await interaction.followup.send("❌ Could not fetch presence data.")
        return
    status_map = {0: "Offline", 1: "Online", 2: "In Game", 3: "In Studio"}
    status_code = presence.get("userPresenceType", 0)
    status_text = status_map.get(status_code, "Unknown")
    embed = discord.Embed(
        title="Presence Debug Info",
        description=f"**Status:** {status_text} ({status_code})",
        color=3447003,
        timestamp=datetime.now(UTC)
    )
    embed.add_field(name="universeId", value=str(presence.get("universeId") or "None"), inline=True)
    embed.add_field(name="placeId", value=str(presence.get("placeId") or "None"), inline=True)
    embed.add_field(name="rootPlaceId", value=str(presence.get("rootPlaceId") or "None"), inline=True)
    embed.add_field(name="Raw Presence", value=f"```json\n{str(presence)[:1000]}\n```", inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="gamehistory", description="Get game history for a user")
@app_commands.describe(roblox_id="The Roblox user ID", limit="Number of games to show (default: 25)")
async def gamehistory(interaction: discord.Interaction, roblox_id: str, limit: int = 25):
    await interaction.response.defer()
    user_info = get_user_info(roblox_id)
    if not user_info:
        await interaction.followup.send(f"❌ Could not find Roblox user with ID: {roblox_id}")
        return
    username = user_info.get("name", "Unknown")
    unique_games = get_unique_games(roblox_id, limit)
    if not unique_games:
        await interaction.followup.send(f"No game history found for {username}.")
        return
    profile_url = f"https://www.roblox.com/users/{roblox_id}/profile"
    embed = discord.Embed(
        title=f"Game History for {username}",
        description=f"Total unique games: {len(unique_games)}\n[View Profile]({profile_url})",
        color=3447003,
        timestamp=datetime.now(UTC)
    )
    game_entries = []
    for game_name, play_count, last_played in unique_games[:limit]:
        try:
            if isinstance(last_played, str):
                if 'Z' in last_played:
                    dt = datetime.fromisoformat(last_played.replace('Z', '+00:00'))
                else:
                    dt = datetime.fromisoformat(last_played)
            else:
                dt = last_played
            formatted_time = dt.strftime("%m/%d/%Y, %I:%M:%S %p")
        except:
            formatted_time = str(last_played) if last_played else "Unknown"
        game_entries.append(f"**{game_name}**\n{username} - {formatted_time}")
    chunk_size = 5
    for i in range(0, len(game_entries), chunk_size):
        chunk = game_entries[i:i + chunk_size]
        embed.add_field(
            name=f"Games ({i+1}-{min(i+chunk_size, len(game_entries))})",
            value="\n\n".join(chunk),
            inline=False
        )
    embed.set_footer(text=f"Page 1/1 • Total games: {len(unique_games)}", icon_url="https://www.roblox.com/favicon.ico")
    embed.set_author(
        name=username,
        url=profile_url,
        icon_url=f"https://www.roblox.com/headshot-thumbnail/image?userId={roblox_id}&width=420&height=420&format=png"
    )
    await interaction.followup.send(embed=embed)

if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Please set DISCORD_BOT_TOKEN in config.py")
        exit(1)
    bot.run(DISCORD_BOT_TOKEN)
