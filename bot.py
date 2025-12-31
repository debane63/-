import asyncio
import random
import logging
import os
import json
import secrets
import string
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import requests

# ==================== CONFIGURATION ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# API configurations
MOBILE_API_URL = "https://hitackgrop.vercel.app/get_data"
MOBILE_API_KEY = "Demo"
PAN_API_URL = "https://pan.amorinthz.workers.dev/"
PAK_API_URL = "https://paknum.amorinthz.workers.dev/"

# Channel configuration
CHANNEL_USERNAME = "CEXIDEX"
CHANNEL_LINK = f"https://t.me/{CHANNEL_USERNAME}"
CHANNEL_ID = f"@{CHANNEL_USERNAME}"

# Admin configuration - আপনার Telegram ID এখানে দিন
ADMIN_IDS = [123456789]  # আপনার আসল ID দিন

# User data storage
user_data = {}
user_credits = {}
verified_users = set()
first_welcome_sent = set()
sent_notifications = set()
banned_users = set()

# Redeem codes storage
redeem_codes = {}
used_codes = {}

# Track user's current action
user_current_action = {}

# ==================== DATA PERSISTENCE ====================
DATA_FILE = "bot_data.json"

def save_data():
    """Save all data to file"""
    data = {
        'user_data': user_data,
        'user_credits': user_credits,
        'verified_users': list(verified_users),
        'first_welcome_sent': list(first_welcome_sent),
        'sent_notifications': list(sent_notifications),
        'banned_users': list(banned_users),
        'redeem_codes': redeem_codes,
        'used_codes': {uid: list(codes) for uid, codes in used_codes.items()}
    }
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, default=str)
        print("✅ Data saved successfully")
    except Exception as e:
        print(f"❌ Error saving data: {e}")

def load_data():
    """Load all data from file"""
    global user_data, user_credits, verified_users, first_welcome_sent
    global sent_notifications, banned_users, redeem_codes, used_codes
    
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        
        user_data = data.get('user_data', {})
        user_credits = data.get('user_credits', {})
        verified_users = set(data.get('verified_users', []))
        first_welcome_sent = set(data.get('first_welcome_sent', []))
        sent_notifications = set(data.get('sent_notifications', []))
        banned_users = set(data.get('banned_users', []))
        redeem_codes = data.get('redeem_codes', {})
        used_codes = {uid: set(codes) for uid, codes in data.get('used_codes', {}).items()}
        
        print("✅ Data loaded successfully")
    except FileNotFoundError:
        print("ℹ️ No data file found, starting fresh")
    except Exception as e:
        print(f"❌ Error loading data: {e}")

# ==================== HELPER FUNCTIONS ====================
def is_admin(user_id):
    """Check if user is admin"""
    return user_id in ADMIN_IDS

def generate_redeem_code(length=12):
    """Generate a redeem code"""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def get_system_stats():
    """Get system statistics"""
    total_users = len(user_data)
    verified_users_count = len(verified_users)
    banned_users_count = len(banned_users)
    
    total_searches = 0
    total_credits = 0
    
    for uid in user_data:
        total_searches += user_data[uid].get('search_count', 0)
        total_searches += user_data[uid].get('pan_search_count', 0)
        total_searches += user_data[uid].get('pak_search_count', 0)
        total_credits += user_credits.get(uid, 0)
    
    avg_credits = total_credits / total_users if total_users > 0 else 0
    active_codes = len([c for c in redeem_codes if len(redeem_codes[c].get('used_by', set())) < redeem_codes[c].get('max_uses', 1)])
    
    return {
        'total_users': total_users,
        'verified_users': verified_users_count,
        'banned_users': banned_users_count,
        'active_codes': active_codes,
        'total_searches': total_searches,
        'total_credits': total_credits,
        'avg_credits': round(avg_credits, 2)
    }

# ==================== CHANNEL MANAGEMENT ====================
async def check_channel_membership(user_id, context):
    """Check if user is currently member of channel"""
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"❌ Channel check error: {e}")
        return False

async def send_channel_notification(context, user, action="joined"):
    """Send notification to channel when user joins/leaves"""
    try:
        if action == "joined":
            message = f"<b>📢 NEW MEMBER JOINED</b>\n\n<b>👤 Name:</b> {user.full_name}\n<b>🆔 ID:</b> <code>{user.id}</code>\n<b>📛 Username:</b> @{user.username if user.username else 'No username'}\n<b>⏰ Time:</b> {datetime.now().strftime('%I:%M %p')}"
            sent_notifications.add(user.id)
        else:
            message = f"<b>👋 MEMBER LEFT</b>\n\n<b>👤 Name:</b> {user.full_name}\n<b>🆔 ID:</b> <code>{user.id}</code>\n<b>📛 Username:</b> @{user.username if user.username else 'No username'}\n<b>⏰ Time:</b> {datetime.now().strftime('%I:%M %p')}"
        
        await context.bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode='HTML')
        return True
    except Exception as e:
        print(f"❌ Notification failed: {e}")
        return False

# ==================== START COMMAND ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    
    if user_id in banned_users:
        await update.message.reply_text("🚫 <b>ACCOUNT BANNED</b>\n\nYour account has been banned by admin.", parse_mode='HTML')
        return
    
    context.user_data['user_info'] = user
    
    if user_id in verified_users:
        is_member = await check_channel_membership(user_id, context)
        if is_member:
            await send_welcome_gif(context, user)
            await show_main_menu(update, user_id, user)
            return
        else:
            verified_users.discard(user_id)
            first_welcome_sent.discard(user_id)
    
    is_member = await check_channel_membership(user_id, context)
    
    if is_member:
        await show_verification_screen(update, user)
    else:
        await show_join_screen(update, user)

async def send_welcome_gif(context, user, is_rejoin=False):
    """Send welcome GIF"""
    try:
        if user.id in first_welcome_sent and not is_rejoin:
            return
        
        welcome_gifs = [
            "https://media.giphy.com/media/3o7abAHdYvZdBNnGZq/giphy.gif",
            "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif",
            "https://media.giphy.com/media/26tknCqiJrBQG6DrC/giphy.gif",
        ]
        
        gif_url = random.choice(welcome_gifs)
        
        caption = f"<b>✨ WELCOME {user.full_name}! ✨</b>\n\n"
        
        if is_rejoin:
            caption += f"<b>🔄 Welcome back to Tracker Pro!</b>\n\n"
        
        caption += f"""<b>👤 User Information:</b>
• <b>Name:</b> {user.full_name}
• <b>Username:</b> @{user.username if user.username else 'Not set'}
• <b>ID:</b> <code>{user.id}</code>

<b>💰 Account Status:</b>
• <b>Credits:</b> <code>{user_credits.get(user.id, 10)}</code>
• <b>Cost per search:</b> 1 credit

<b>🎯 Ready to explore premium features!</b>"""
        
        await context.bot.send_animation(chat_id=user.id, animation=gif_url, caption=caption, parse_mode='HTML')
        first_welcome_sent.add(user.id)
        
    except Exception as e:
        print(f"❌ GIF error: {e}")

async def show_join_screen(update: Update, user):
    """Show channel join screen"""
    join_message = f"""<b>🔐 ACCESS REQUIRED</b>
━━━━━━━━━━━━━━━━━━━━

<b>👋 Hello, {user.full_name}!</b>

Join our channel to unlock <b>Tracker Pro</b> features.

<b>📋 Quick Steps:</b>
1. Join channel (click below)
2. Return here
3. Click VERIFY

<b>🎁 Get 10 FREE credits instantly!</b>

━━━━━━━━━━━━━━━━━━━━"""
    
    keyboard = [
        [InlineKeyboardButton("🌟 JOIN CHANNEL 🌟", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ VERIFY MEMBERSHIP", callback_data='verify_join')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(join_message, reply_markup=reply_markup, parse_mode='HTML')
    else:
        query = update.callback_query
        await query.edit_message_text(join_message, reply_markup=reply_markup, parse_mode='HTML')

async def show_verification_screen(update: Update, user):
    """Show verification screen"""
    verify_message = f"""<b>🔐 VERIFICATION REQUIRED</b>
━━━━━━━━━━━━━━━━━━━━

<b>👋 Welcome, {user.full_name}!</b>

Click verify to activate your account.

<b>🎁 Get 10 FREE credits instantly!</b>

━━━━━━━━━━━━━━━━━━━━"""
    
    keyboard = [
        [InlineKeyboardButton("✅ CLICK TO VERIFY", callback_data='verify_join')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(verify_message, reply_markup=reply_markup, parse_mode='HTML')
    else:
        query = update.callback_query
        await query.edit_message_text(verify_message, reply_markup=reply_markup, parse_mode='HTML')

async def verify_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify user membership"""
    query = update.callback_query
    user = query.from_user
    user_id = user.id
    
    if user_id in banned_users:
        await query.answer("🚫 Your account is banned!", show_alert=True)
        return
    
    await query.answer()
    
    is_member = await check_channel_membership(user_id, context)
    
    if is_member:
        verified_users.add(user_id)
        
        if user_id not in user_data:
            user_data[user_id] = {
                'name': user.full_name,
                'username': user.username,
                'join_date': datetime.now(),
                'channel_status': 'member',
                'search_count': 0,
                'pan_search_count': 0,
                'pak_search_count': 0
            }
            await send_channel_notification(context, user, "joined")
        else:
            user_data[user_id]['channel_status'] = 'member'
        
        if user_id not in user_credits:
            user_credits[user_id] = 10
        
        await query.delete_message()
        
        is_rejoin = user_id in first_welcome_sent
        await send_welcome_gif(context, user, is_rejoin=is_rejoin)
        
        await asyncio.sleep(1)
        await show_main_menu(update, user_id, user)
    else:
        await query.answer("❌ Join the channel first!", show_alert=True)
        await show_join_screen(update, user)

# ==================== MAIN MENU ====================
async def show_main_menu(update, user_id, user):
    """Show main menu"""
    welcome_message = f"""<b>🚀 TRACKER PRO DASHBOARD</b>
━━━━━━━━━━━━━━━━━━━━

<b>👤 Welcome, {user.full_name}!</b>

<b>💰 CREDIT STATUS</b>
• <b>Available:</b> <code>{user_credits.get(user_id, 0)}</code> credits
• <b>Cost per search:</b> 1 credit

<b>📊 YOUR STATISTICS</b>
• <b>Mobile Searches:</b> {user_data[user_id]['search_count']}
• <b>PAN Searches:</b> {user_data[user_id]['pan_search_count']}
• <b>PAK Searches:</b> {user_data[user_id]['pak_search_count']}

━━━━━━━━━━━━━━━━━━━━
<b>🔍 SELECT SERVICE:</b>"""
    
    keyboard = [
        ["🔍 Search Mobile"],
        ["🏦 PAN Information"],
        ["🇵🇰 PAK Information"]
    ]
    
    if is_admin(user_id):
        keyboard.append(["⚙️ Admin Panel"])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='HTML')

# ==================== ADMIN PANEL ====================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ <b>ACCESS DENIED</b>\n\nYou are not authorized.", parse_mode='HTML')
        return
    
    stats = get_system_stats()
    
    admin_message = f"""<b>⚙️ ADMIN CONTROL PANEL</b>
━━━━━━━━━━━━━━━━━━━━

<b>📊 SYSTEM STATISTICS</b>
• Total Users: <code>{stats['total_users']}</code>
• Verified Users: <code>{stats['verified_users']}</code>
• Banned Users: <code>{stats['banned_users']}</code>
• Active Codes: <code>{stats['active_codes']}</code>
• Total Searches: <code>{stats['total_searches']}</code>

<b>💰 CREDITS SUMMARY</b>
• Total Credits Issued: <code>{stats['total_credits']}</code>
• Average Credits per User: <code>{stats['avg_credits']}</code>

━━━━━━━━━━━━━━━━━━━━
<b>👤 USER MANAGEMENT</b>
━━━━━━━━━━━━━━━━━━━━
<b>Select an action:</b>"""
    
    keyboard = [
        ["➕ Add Credits", "➖ Remove Credits"],
        ["👤 User Details", "📊 User Stats"],
        ["🚫 Ban User", "✅ Unban User"],
        ["🎫 Generate Codes", "📋 View Codes"],
        ["⬅️ Back to Main"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    await update.message.reply_text(admin_message, reply_markup=reply_markup, parse_mode='HTML')

async def show_user_stats(update: Update):
    """Show user statistics"""
    stats = get_system_stats()
    
    top_users = sorted(user_credits.items(), key=lambda x: x[1], reverse=True)[:10]
    
    top_users_text = ""
    for idx, (uid, credits) in enumerate(top_users, 1):
        name = user_data.get(uid, {}).get('name', 'Unknown')
        top_users_text += f"{idx}. <code>{uid}</code> - {name}: <b>{credits}</b> credits\n"
    
    stats_message = f"""<b>📊 USER STATISTICS</b>
━━━━━━━━━━━━━━━━━━━━

<b>👥 USER DISTRIBUTION</b>
• Total Users: <code>{stats['total_users']}</code>
• Verified: <code>{stats['verified_users']}</code> ({stats['verified_users']/stats['total_users']*100:.1f}%)
• Banned: <code>{stats['banned_users']}</code> ({stats['banned_users']/stats['total_users']*100:.1f}%)

<b>💰 CREDITS DISTRIBUTION</b>
• Total Credits Issued: <code>{stats['total_credits']}</code>
• Average per User: <code>{stats['avg_credits']}</code>

<b>🔍 SEARCH ACTIVITY</b>
• Total Searches: <code>{stats['total_searches']}</code>
• Average per User: <code>{stats['total_searches']/stats['total_users']:.1f}</code>

<b>🏆 TOP 10 USERS (BY CREDITS)</b>
{top_users_text if top_users_text else "No data available"}

<b>🎫 REDEEM CODES</b>
• Active Codes: <code>{stats['active_codes']}</code>
• Total Codes: <code>{len(redeem_codes)}</code>"""
    
    await update.message.reply_text(stats_message, parse_mode='HTML')

async def show_all_codes(update: Update):
    """Show all redeem codes"""
    if not redeem_codes:
        await update.message.reply_text("❌ No redeem codes available.", parse_mode='HTML')
        return
    
    active_codes = []
    expired_codes = []
    
    for code, details in redeem_codes.items():
        used_count = len(details.get('used_by', set()))
        max_uses = details.get('max_uses', 1)
        
        if used_count < max_uses:
            active_codes.append((code, details))
        else:
            expired_codes.append((code, details))
    
    message = "<b>🎫 REDEEM CODES LIST</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    if active_codes:
        message += f"<b>✅ ACTIVE CODES ({len(active_codes)})</b>\n"
        for code, details in active_codes[:20]:
            used = len(details.get('used_by', set()))
            max_uses = details.get('max_uses', 1)
            message += f"• <code>{code}</code> - {details['credits']} credits ({used}/{max_uses} uses)\n"
    
    if expired_codes:
        message += f"\n<b>❌ EXPIRED CODES ({len(expired_codes)})</b>\n"
        for code, details in expired_codes[:10]:
            used = len(details.get('used_by', set()))
            message += f"• <code>{code}</code> - {details['credits']} credits (FULLY USED)\n"
    
    message += f"\n<b>📊 SUMMARY:</b>\n"
    message += f"• Total Codes: <code>{len(redeem_codes)}</code>\n"
    message += f"• Active Codes: <code>{len(active_codes)}</code>\n"
    message += f"• Expired Codes: <code>{len(expired_codes)}</code>\n"
    message += f"• Total Credits Available: <code>{sum(d['credits'] for d in redeem_codes.values())}</code>"
    
    await update.message.reply_text(message, parse_mode='HTML')

# ==================== ADMIN ACTIONS ====================
async def process_add_credits(update: Update, text: str, admin_id: int):
    """Process adding credits to user"""
    try:
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("❌ Invalid format. Use: user_id amount", parse_mode='HTML')
            return
        
        target_id = int(parts[0])
        amount = int(parts[1])
        
        if target_id not in user_credits:
            user_credits[target_id] = 0
        
        user_credits[target_id] += amount
        
        try:
            await update._bot.send_message(
                chat_id=target_id,
                text=f"🎁 <b>CREDITS ADDED!</b>\n\nAdmin added <code>{amount}</code> credits.\n<b>Total:</b> <code>{user_credits[target_id]}</code>",
                parse_mode='HTML'
            )
        except:
            pass
        
        await update.message.reply_text(
            f"✅ <b>CREDITS ADDED</b>\n\n"
            f"• User ID: <code>{target_id}</code>\n"
            f"• Amount: <code>+{amount}</code>\n"
            f"• New Balance: <code>{user_credits[target_id]}</code>",
            parse_mode='HTML'
        )
        
        save_data()
        
    except ValueError:
        await update.message.reply_text("❌ Invalid input. Use numbers only.", parse_mode='HTML')

async def process_remove_credits(update: Update, text: str, admin_id: int):
    """Process removing credits from user"""
    try:
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("❌ Invalid format. Use: user_id amount", parse_mode='HTML')
            return
        
        target_id = int(parts[0])
        amount = int(parts[1])
        
        if target_id not in user_credits:
            await update.message.reply_text("❌ User not found.", parse_mode='HTML')
            return
        
        if user_credits[target_id] < amount:
            await update.message.reply_text(f"❌ User has only <code>{user_credits[target_id]}</code> credits.", parse_mode='HTML')
            return
        
        user_credits[target_id] -= amount
        
        try:
            await update._bot.send_message(
                chat_id=target_id,
                text=f"⚠️ <b>CREDITS REMOVED</b>\n\nAdmin removed <code>{amount}</code> credits.\n<b>Total:</b> <code>{user_credits[target_id]}</code>",
                parse_mode='HTML'
            )
        except:
            pass
        
        await update.message.reply_text(
            f"✅ <b>CREDITS REMOVED</b>\n\n"
            f"• User ID: <code>{target_id}</code>\n"
            f"• Amount: <code>-{amount}</code>\n"
            f"• New Balance: <code>{user_credits[target_id]}</code>",
            parse_mode='HTML'
        )
        
        save_data()
        
    except ValueError:
        await update.message.reply_text("❌ Invalid input. Use numbers only.", parse_mode='HTML')

async def show_user_details(update: Update, user_input: str):
    """Show user details"""
    try:
        target_id = int(user_input)
        
        if target_id not in user_data:
            await update.message.reply_text("❌ User not found.", parse_mode='HTML')
            return
        
        user_info = user_data[target_id]
        credits = user_credits.get(target_id, 0)
        is_verified = target_id in verified_users
        is_banned = target_id in banned_users
        
        details = f"""<b>👤 USER DETAILS</b>
━━━━━━━━━━━━━━━━━━━━

<b>🔑 BASIC INFO</b>
• <b>ID:</b> <code>{target_id}</code>
• <b>Name:</b> {user_info.get('name', 'N/A')}
• <b>Username:</b> @{user_info.get('username', 'N/A')}
• <b>Joined:</b> {user_info.get('join_date', 'N/A')}

<b>📊 STATUS</b>
• <b>Verified:</b> {'✅ Yes' if is_verified else '❌ No'}
• <b>Banned:</b> {'🚫 Yes' if is_banned else '✅ No'}
• <b>Credits:</b> <code>{credits}</code>

<b>🔍 ACTIVITY</b>
• <b>Mobile Searches:</b> {user_info.get('search_count', 0)}
• <b>PAN Searches:</b> {user_info.get('pan_search_count', 0)}
• <b>PAK Searches:</b> {user_info.get('pak_search_count', 0)}
• <b>Total Searches:</b> {user_info.get('search_count', 0) + user_info.get('pan_search_count', 0) + user_info.get('pak_search_count', 0)}

<b>💎 REDEEM HISTORY</b>
• <b>Codes Used:</b> {len(used_codes.get(target_id, set()))}"""
        
        await update.message.reply_text(details, parse_mode='HTML')
        
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Use numbers only.", parse_mode='HTML')

async def process_ban_user(update: Update, text: str, admin_id: int):
    """Process banning a user"""
    try:
        target_id = int(text)
        
        if target_id in ADMIN_IDS:
            await update.message.reply_text("❌ Cannot ban an admin.", parse_mode='HTML')
            return
        
        banned_users.add(target_id)
        verified_users.discard(target_id)
        
        try:
            await update._bot.send_message(
                chat_id=target_id,
                text="🚫 <b>ACCOUNT BANNED</b>\n\nYour account has been banned by admin.\nYou can no longer use the bot.",
                parse_mode='HTML'
            )
        except:
            pass
        
        await update.message.reply_text(
            f"✅ <b>USER BANNED</b>\n\n"
            f"• User ID: <code>{target_id}</code>\n"
            f"• Name: {user_data.get(target_id, {}).get('name', 'Unknown')}\n"
            f"• Total Banned Users: <code>{len(banned_users)}</code>",
            parse_mode='HTML'
        )
        
        save_data()
        
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.", parse_mode='HTML')

async def process_unban_user(update: Update, text: str, admin_id: int):
    """Process unbanning a user"""
    try:
        target_id = int(text)
        
        if target_id not in banned_users:
            await update.message.reply_text("❌ User is not banned.", parse_mode='HTML')
            return
        
        banned_users.discard(target_id)
        
        try:
            await update._bot.send_message(
                chat_id=target_id,
                text="✅ <b>ACCOUNT UNBANNED</b>\n\nYour account has been unbanned by admin.\nYou can now use the bot again.",
                parse_mode='HTML'
            )
        except:
            pass
        
        await update.message.reply_text(
            f"✅ <b>USER UNBANNED</b>\n\n"
            f"• User ID: <code>{target_id}</code>\n"
            f"• Name: {user_data.get(target_id, {}).get('name', 'Unknown')}\n"
            f"• Total Banned Users: <code>{len(banned_users)}</code>",
            parse_mode='HTML'
        )
        
        save_data()
        
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.", parse_mode='HTML')

async def process_generate_codes(update: Update, text: str, admin_id: int):
    """Process generating redeem codes"""
    try:
        parts = text.split()
        if len(parts) != 3:
            await update.message.reply_text("❌ Invalid format. Use: amount credits max_uses", parse_mode='HTML')
            return
        
        amount = int(parts[0])
        credits = int(parts[1])
        max_uses = int(parts[2])
        
        if amount > 100:
            await update.message.reply_text("❌ Maximum 100 codes at a time.", parse_mode='HTML')
            return
        
        codes_list = []
        for i in range(amount):
            code = generate_redeem_code()
            redeem_codes[code] = {
                'credits': credits,
                'used_by': set(),
                'max_uses': max_uses,
                'created_by': admin_id,
                'created_at': datetime.now().isoformat()
            }
            codes_list.append(code)
        
        save_data()
        
        codes_text = ""
        for idx, code in enumerate(codes_list, 1):
            codes_text += f"{idx}. <code>{code}</code>\n"
        
        await update.message.reply_text(
            f"✅ <b>REDEEM CODES GENERATED</b>\n\n"
            f"• Amount: <code>{amount}</code>\n"
            f"• Credits per code: <code>{credits}</code>\n"
            f"• Max uses per code: <code>{max_uses}</code>\n\n"
            f"<b>📋 GENERATED CODES:</b>\n"
            f"{codes_text}\n"
            f"<b>📝 Share with users: /redeem CODE</b>",
            parse_mode='HTML'
        )
        
    except ValueError:
        await update.message.reply_text("❌ Invalid input. Use numbers only.", parse_mode='HTML')

# ==================== REDEEM COMMAND ====================
async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /redeem command"""
    user_id = update.effective_user.id
    
    if user_id in banned_users:
        await update.message.reply_text("🚫 <b>ACCOUNT BANNED</b>\n\nYour account has been banned.", parse_mode='HTML')
        return
    
    if len(context.args) == 0:
        await update.message.reply_text(
            "🎫 <b>REDEEM CODE</b>\n\n"
            "Usage: <code>/redeem CODE</code>\n\n"
            "<b>Example:</b> <code>/redeem ABC123DEF456</code>\n\n"
            "Enter the redeem code provided by admin.",
            parse_mode='HTML'
        )
        return
    
    code = context.args[0].upper().strip()
    
    if code not in redeem_codes:
        await update.message.reply_text("❌ <b>INVALID CODE</b>\n\nThe redeem code is invalid.", parse_mode='HTML')
        return
    
    code_details = redeem_codes[code]
    
    if user_id in code_details.get('used_by', set()):
        await update.message.reply_text("❌ <b>CODE ALREADY USED</b>\n\nYou have already used this code.", parse_mode='HTML')
        return
    
    used_count = len(code_details.get('used_by', set()))
    max_uses = code_details.get('max_uses', 1)
    
    if used_count >= max_uses:
        await update.message.reply_text("❌ <b>CODE EXPIRED</b>\n\nThis code has reached its limit.", parse_mode='HTML')
        return
    
    credits_to_add = code_details['credits']
    
    if user_id not in user_credits:
        user_credits[user_id] = 0
    
    user_credits[user_id] += credits_to_add
    code_details['used_by'].add(user_id)
    
    if user_id not in used_codes:
        used_codes[user_id] = set()
    used_codes[user_id].add(code)
    
    save_data()
    
    await update.message.reply_text(
        f"🎉 <b>REDEEM SUCCESSFUL!</b>\n\n"
        f"✅ You received <code>{credits_to_add}</code> credits!\n\n"
        f"<b>📊 ACCOUNT STATUS:</b>\n"
        f"• Previous Credits: <code>{user_credits[user_id] - credits_to_add}</code>\n"
        f"• Added Credits: <code>+{credits_to_add}</code>\n"
        f"• New Balance: <code>{user_credits[user_id]}</code>\n\n"
        f"<b>🎫 CODE INFO:</b>\n"
        f"• Code: <code>{code}</code>\n"
        f"• Uses Left: <code>{max_uses - used_count - 1}</code>\n\n"
        f"<b>💎 Happy searching!</b>",
        parse_mode='HTML'
    )

# ==================== MESSAGE HANDLER ====================
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if user_id in banned_users:
        await update.message.reply_text("🚫 <b>ACCOUNT BANNED</b>\n\nYour account has been banned.", parse_mode='HTML')
        return
    
    # ========== ADMIN HANDLING ==========
    if is_admin(user_id):
        current_action = user_current_action.get(user_id)
        
        # Admin panel buttons
        if text == "⚙️ Admin Panel":
            await admin_panel(update, context)
            return
            
        elif text == "➕ Add Credits":
            user_current_action[user_id] = "add_credits"
            await update.message.reply_text("💎 <b>ADD CREDITS</b>\n\nEnter: user_id amount\n<b>Example:</b> 123456789 50", parse_mode='HTML')
            return
            
        elif text == "➖ Remove Credits":
            user_current_action[user_id] = "remove_credits"
            await update.message.reply_text("💎 <b>REMOVE CREDITS</b>\n\nEnter: user_id amount\n<b>Example:</b> 123456789 20", parse_mode='HTML')
            return
            
        elif text == "👤 User Details":
            user_current_action[user_id] = "user_details"
            await update.message.reply_text("👤 <b>USER DETAILS</b>\n\nEnter user ID:", parse_mode='HTML')
            return
            
        elif text == "📊 User Stats":
            await show_user_stats(update)
            return
            
        elif text == "🚫 Ban User":
            user_current_action[user_id] = "ban_user"
            await update.message.reply_text("🚫 <b>BAN USER</b>\n\nEnter user ID to ban:", parse_mode='HTML')
            return
            
        elif text == "✅ Unban User":
            user_current_action[user_id] = "unban_user"
            await update.message.reply_text("✅ <b>UNBAN USER</b>\n\nEnter user ID to unban:", parse_mode='HTML')
            return
            
        elif text == "🎫 Generate Codes":
            user_current_action[user_id] = "generate_codes"
            await update.message.reply_text("🎫 <b>GENERATE CODES</b>\n\nEnter: amount credits max_uses\n<b>Example:</b> 10 10 1", parse_mode='HTML')
            return
            
        elif text == "📋 View Codes":
            await show_all_codes(update)
            return
            
        elif text == "⬅️ Back to Main":
            user_current_action[user_id] = None
            await show_main_menu(update, user_id, update.effective_user)
            return
        
        # Process admin actions
        if current_action == "add_credits":
            await process_add_credits(update, text, user_id)
            user_current_action[user_id] = None
            return
            
        elif current_action == "remove_credits":
            await process_remove_credits(update, text, user_id)
            user_current_action[user_id] = None
            return
            
        elif current_action == "user_details":
            await show_user_details(update, text)
            user_current_action[user_id] = None
            return
            
        elif current_action == "ban_user":
            await process_ban_user(update, text, user_id)
            user_current_action[user_id] = None
            return
            
        elif current_action == "unban_user":
            await process_unban_user(update, text, user_id)
            user_current_action[user_id] = None
            return
            
        elif current_action == "generate_codes":
            await process_generate_codes(update, text, user_id)
            user_current_action[user_id] = None
            return
    
    # ========== NORMAL USER FLOW ==========
    if user_id not in verified_users:
        await update.message.reply_text("⚠️ <b>VERIFICATION REQUIRED</b>\n\nUse /start to verify.", parse_mode='HTML')
        return
    
    is_member = await check_channel_membership(user_id, context)
    if not is_member:
        verified_users.discard(user_id)
        await update.message.reply_text("❌ <b>MEMBERSHIP EXPIRED</b>\n\nUse /start to rejoin.", parse_mode='HTML')
        return
    
    # User menu buttons
    if text == "🔍 Search Mobile":
        user_current_action[user_id] = "mobile_search"
        await search_mobile_number(update, user_id)
        
    elif text == "🏦 PAN Information":
        user_current_action[user_id] = "pan_search"
        await search_pan_info(update, user_id)
        
    elif text == "🇵🇰 PAK Information":
        user_current_action[user_id] = "pak_search"
        await search_pak_info(update, user_id)
        
    elif text == "⬅️ Back":
        await show_main_menu(update, user_id, update.effective_user)
        
    else:
        current_action = user_current_action.get(user_id)
        
        if current_action == "mobile_search":
            if text.isdigit() and len(text) == 10:
                await process_mobile_search(update, context, text, user_id)
            else:
                await update.message.reply_text("❌ Enter 10-digit number.\n<b>Example:</b> 9876543210", parse_mode='HTML')
                
        elif current_action == "pan_search":
            if len(text) == 10 and text.isalnum():
                await process_pan_search(update, context, text, user_id)
            else:
                await update.message.reply_text("❌ Enter 10-character PAN.\n<b>Example:</b> EJVPG4183G", parse_mode='HTML')
                
        elif current_action == "pak_search":
            if text.isdigit() and len(text) == 10:
                await process_pak_search(update, context, text, user_id)
            else:
                await update.message.reply_text("❌ Enter 10-digit PAK number.\n<b>Example:</b> 3014819864", parse_mode='HTML')

# ==================== SEARCH FUNCTIONS ====================
async def search_mobile_number(update: Update, user_id: int):
    """Show mobile search interface"""
    if user_credits.get(user_id, 0) <= 0:
        await update.message.reply_text("❌ <b>NO CREDITS</b>\n\nYou have 0 credits.\nUse /redeem to add more.", parse_mode='HTML')
        return
    
    search_message = f"""<b>🔍 MOBILE SEARCH</b>
━━━━━━━━━━━━━━━━━━━━

<b>💰 Credits:</b> <code>{user_credits[user_id]}</code>
<b>💎 Cost:</b> 1 credit

<b>📝 Enter 10-digit mobile number:</b>

<b>Example:</b> <code>9876543210</code>

━━━━━━━━━━━━━━━━━━━━"""
    
    keyboard = [["⬅️ Back"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text(search_message, reply_markup=reply_markup, parse_mode='HTML')

async def search_pan_info(update: Update, user_id: int):
    """Show PAN search interface"""
    if user_credits.get(user_id, 0) <= 0:
        await update.message.reply_text("❌ <b>NO CREDITS</b>\n\nYou have 0 credits.\nUse /redeem to add more.", parse_mode='HTML')
        return
    
    search_message = f"""<b>🏦 PAN SEARCH</b>
━━━━━━━━━━━━━━━━━━━━

<b>💰 Credits:</b> <code>{user_credits[user_id]}</code>
<b>💎 Cost:</b> 1 credit

<b>📝 Enter 10-character PAN:</b>

<b>Example:</b> <code>EJVPG4183G</code>

━━━━━━━━━━━━━━━━━━━━"""
    
    keyboard = [["⬅️ Back"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text(search_message, reply_markup=reply_markup, parse_mode='HTML')

async def search_pak_info(update: Update, user_id: int):
    """Show PAK search interface"""
    if user_credits.get(user_id, 0) <= 0:
        await update.message.reply_text("❌ <b>NO CREDITS</b>\n\nYou have 0 credits.\nUse /redeem to add more.", parse_mode='HTML')
        return
    
    search_message = f"""<b>🇵🇰 PAKISTAN MOBILE SEARCH</b>
━━━━━━━━━━━━━━━━━━━━

<b>💰 Credits:</b> <code>{user_credits[user_id]}</code>
<b>💎 Cost:</b> 1 credit

<b>📝 Enter 10-digit Pakistan mobile number:</b>

<b>Example:</b> <code>3014819864</code>

━━━━━━━━━━━━━━━━━━━━"""
    
    keyboard = [["⬅️ Back"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text(search_message, reply_markup=reply_markup, parse_mode='HTML')

# ==================== API FUNCTIONS ====================
def fetch_mobile_data(mobile_number):
    """Fetch data from mobile API"""
    try:
        url_formats = [
            f"{MOBILE_API_URL}?key={MOBILE_API_KEY}&mobile={mobile_number}",
            f"https://hitackgrop.vercel.app/get_data?key=Demo&mobile={mobile_number}",
            f"https://hitackgrop.vercel.app/get_data?mobile={mobile_number}"
        ]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        for full_url in url_formats:
            try:
                response = requests.get(full_url, headers=headers, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if isinstance(data, dict):
                        if 'data' in data and 'result' in data['data']:
                            results = data['data']['result']
                            if results and len(results) > 0:
                                return results[0]
                        
                        elif 'result' in data and isinstance(data['result'], list) and len(data['result']) > 0:
                            return data['result'][0]
                        
                        elif 'success' in data and data['success']:
                            for key, value in data.items():
                                if isinstance(value, list) and len(value) > 0:
                                    if isinstance(value[0], dict) and 'name' in value[0]:
                                        return value[0]
                        
                        elif 'name' in data or 'mobile' in data:
                            return data
                    
                    elif isinstance(data, list) and len(data) > 0:
                        if isinstance(data[0], dict) and ('name' in data[0] or 'mobile' in data[0]):
                            return data[0]
                            
            except:
                continue
        
        return None
            
    except Exception as e:
        print(f"❌ Mobile API error: {e}")
        return None

def fetch_pan_data(pan_number):
    """Fetch PAN data"""
    try:
        url = f"{PAN_API_URL}?key=AMORINTH&pan={pan_number}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            return response.json()
        
        return None
    except Exception as e:
        print(f"❌ PAN API error: {e}")
        return None

def fetch_pak_data(phone_number):
    """Fetch Pakistan mobile data"""
    try:
        url = f"{PAK_API_URL}?key=AMORINTH&number={phone_number}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            return response.json()
        
        return None
    except Exception as e:
        print(f"❌ PAK API error: {e}")
        return None

# ==================== LOADING ANIMATION ====================
async def show_loading_animation(update, search_type, query_text):
    """Professional loading animation"""
    if search_type == "mobile":
        emoji = "📱"
        texts = ["🔍 Searching...", "📊 Fetching...", "⚡ Processing...", "✅ Almost done..."]
    elif search_type == "pan":
        emoji = "🏦"
        texts = ["🔍 Verifying...", "📊 Checking...", "⚡ Processing...", "✅ Almost done..."]
    else:
        emoji = "🇵🇰"
        texts = ["🔍 Searching...", "📊 Accessing...", "⚡ Processing...", "✅ Almost done..."]
    
    msg = await update.message.reply_text(
        f"<b>{emoji} {texts[0]}</b>\n"
        f"<code>Searching: {query_text}</code>\n\n"
        f"▰▱▱▱▱▱▱▱▱▱ 0%",
        parse_mode='HTML'
    )
    
    progress_steps = [
        "▰▱▱▱▱▱▱▱▱▱ 10%",
        "▰▰▱▱▱▱▱▱▱▱ 20%", 
        "▰▰▰▱▱▱▱▱▱▱ 30%",
        "▰▰▰▰▱▱▱▱▱▱ 40%",
        "▰▰▰▰▰▱▱▱▱▱ 50%",
        "▰▰▰▰▰▰▱▱▱▱ 60%",
        "▰▰▰▰▰▰▰▱▱▱ 70%",
        "▰▰▰▰▰▰▰▰▱▱ 80%",
        "▰▰▰▰▰▰▰▰▰▱ 90%",
        "▰▰▰▰▰▰▰▰▰▰ 100%"
    ]
    
    for i in range(10):
        await asyncio.sleep(0.4)
        try:
            text_idx = min(i // 3, len(texts) - 1)
            await msg.edit_text(
                f"<b>{emoji} {texts[text_idx]}</b>\n"
                f"<code>Searching: {query_text}</code>\n\n"
                f"{progress_steps[i]}",
                parse_mode='HTML'
            )
        except:
            pass
    
    return msg

# ==================== PROCESS SEARCHES ====================
async def process_mobile_search(update: Update, context: ContextTypes.DEFAULT_TYPE, mobile_number: str, user_id: int):
    """Process mobile search"""
    if user_credits.get(user_id, 0) <= 0:
        return
    
    loading_msg = await show_loading_animation(update, "mobile", mobile_number)
    data = fetch_mobile_data(mobile_number)
    await loading_msg.delete()
    
    user_credits[user_id] -= 1
    user_data[user_id]['search_count'] += 1
    
    if data:
        result = f"""<b>✅ MOBILE SEARCH RESULT</b>
━━━━━━━━━━━━━━━━━━━━

<b>📱 Number:</b> <code>{mobile_number}</code>

<b>👤 Personal Info:</b>
• <b>Name:</b> {data.get('name', 'N/A')}
• <b>Father:</b> {data.get('father_name', 'N/A')}

<b>📞 Contact:</b>
• <b>Mobile:</b> {data.get('mobile', 'N/A')}
• <b>Alt Mobile:</b> {data.get('alt_mobile', 'N/A')}
• <b>Email:</b> {data.get('email', 'N/A')}

<b>📍 Address:</b>
<pre>{data.get('address', 'N/A').replace('!!', '\n').replace('!', ', ')}</pre>

━━━━━━━━━━━━━━━━━━━━
<b>💰 Credits Left:</b> <code>{user_credits[user_id]}</code>
<b>⏰ Time:</b> {datetime.now().strftime('%I:%M %p')}
<b>📝 Report By:</b> MR D4N"""
    else:
        result = f"""<b>❌ NO DATA FOUND</b>
━━━━━━━━━━━━━━━━━━━━

<b>📱 Searched:</b> <code>{mobile_number}</code>

<b>⚠️ No information available.</b>

━━━━━━━━━━━━━━━━━━━━
<b>💰 Credits Left:</b> <code>{user_credits[user_id]}</code>
<b>⏰ Time:</b> {datetime.now().strftime('%I:%M %p')}
<b>📝 Report By:</b> MR D4N"""
    
    await update.message.reply_text(result, parse_mode='HTML')
    
    keyboard = [
        ["🔍 Search Mobile"],
        ["🏦 PAN Information"],
        ["🇵🇰 PAK Information"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("<b>Choose:</b>", reply_markup=reply_markup, parse_mode='HTML')
    save_data()

async def process_pan_search(update: Update, context: ContextTypes.DEFAULT_TYPE, pan_number: str, user_id: int):
    """Process PAN search"""
    if user_credits.get(user_id, 0) <= 0:
        return
    
    loading_msg = await show_loading_animation(update, "pan", pan_number)
    data = fetch_pan_data(pan_number)
    await loading_msg.delete()
    
    user_credits[user_id] -= 1
    user_data[user_id]['pan_search_count'] += 1
    
    if data and data.get('success'):
        result = f"""<b>✅ PAN CARD INFO</b>
━━━━━━━━━━━━━━━━━━━━

<b>🔢 PAN:</b> <code>{pan_number}</code>
<b>✅ Status:</b> VALID

<b>👤 Details:</b>
• <b>Full Name:</b> {data.get('fullName', 'N/A')}
• <b>First Name:</b> {data.get('firstName', 'N/A')}
• <b>Last Name:</b> {data.get('lastName', 'N/A')}
• <b>Date of Birth:</b> {data.get('dob', 'N/A')}

━━━━━━━━━━━━━━━━━━━━
<b>💰 Credits Left:</b> <code>{user_credits[user_id]}</code>
<b>⏰ Time:</b> {datetime.now().strftime('%I:%M %p')}
<b>📝 Report By:</b> MR D4N"""
    else:
        result = f"""<b>❌ PAN NOT FOUND</b>
━━━━━━━━━━━━━━━━━━━━

<b>🔢 PAN:</b> <code>{pan_number}</code>

<b>⚠️ Invalid or not found.</b>

━━━━━━━━━━━━━━━━━━━━
<b>💰 Credits Left:</b> <code>{user_credits[user_id]}</code>
<b>⏰ Time:</b> {datetime.now().strftime('%I:%M %p')}
<b>📝 Report By:</b> MR D4N"""
    
    await update.message.reply_text(result, parse_mode='HTML')
    
    keyboard = [
        ["🔍 Search Mobile"],
        ["🏦 PAN Information"],
        ["🇵🇰 PAK Information"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("<b>Choose:</b>", reply_markup=reply_markup, parse_mode='HTML')
    save_data()

async def process_pak_search(update: Update, context: ContextTypes.DEFAULT_TYPE, phone_number: str, user_id: int):
    """Process PAK search"""
    if user_credits.get(user_id, 0) <= 0:
        return
    
    loading_msg = await show_loading_animation(update, "pak", phone_number)
    data = fetch_pak_data(phone_number)
    await loading_msg.delete()
    
    user_credits[user_id] -= 1
    user_data[user_id]['pak_search_count'] += 1
    
    if data and data.get('success'):
        records = data.get('records', [])
        
        if records:
            result = f"""<b>✅ PAKISTAN MOBILE SEARCH RESULT</b>
━━━━━━━━━━━━━━━━━━━━

<b>📱 SEARCHED NUMBER</b>
• <b>Phone:</b> <code>{data.get('phone', phone_number)}</code>
• <b>Records Found:</b> {len(records)}

━━━━━━━━━━━━━━━━━━━━
<b>📋 PERSONAL RECORDS</b>"""
            
            for idx, record in enumerate(records, 1):
                result += f"""
<b>📄 Record #{idx}</b>
• <b>Mobile:</b> <code>{record.get('Mobile', 'N/A')}</code>
• <b>Name:</b> {record.get('Name', 'N/A')}
• <b>CNIC:</b> <code>{record.get('CNIC', 'N/A')}</code>
• <b>Country:</b> {record.get('Country', 'N/A')}

<b>📍 Address:</b>
<pre>{record.get('Address', 'N/A')}</pre>
"""
            
            result += f"""
━━━━━━━━━━━━━━━━━━━━
<b>💰 Credits Left:</b> <code>{user_credits[user_id]}</code>
<b>⏰ Time:</b> {datetime.now().strftime('%I:%M %p')}
<b>📝 Report By:</b> MR D4N"""
        else:
            result = f"""<b>✅ SEARCH COMPLETED</b>
━━━━━━━━━━━━━━━━━━━━

<b>📱 SEARCHED NUMBER</b>
• <b>Phone:</b> <code>{phone_number}</code>

<b>⚠️ NO RECORDS FOUND</b>
No information available.

━━━━━━━━━━━━━━━━━━━━
<b>💰 Credits Left:</b> <code>{user_credits[user_id]}</code>
<b>⏰ Time:</b> {datetime.now().strftime('%I:%M %p')}
<b>📝 Report By:</b> MR D4N"""
    else:
        result = f"""<b>❌ SEARCH FAILED</b>
━━━━━━━━━━━━━━━━━━━━

<b>📱 SEARCHED NUMBER</b>
• <b>Phone:</b> <code>{phone_number}</code>

<b>⚠️ API ERROR</b>
Please check the number.

━━━━━━━━━━━━━━━━━━━━
<b>💰 Credits Left:</b> <code>{user_credits[user_id]}</code>
<b>⏰ Time:</b> {datetime.now().strftime('%I:%M %p')}
<b>📝 Report By:</b> MR D4N"""
    
    await update.message.reply_text(result, parse_mode='HTML')
    
    keyboard = [
        ["🔍 Search Mobile"],
        ["🏦 PAN Information"],
        ["🇵🇰 PAK Information"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("<b>Choose:</b>", reply_markup=reply_markup, parse_mode='HTML')
    save_data()

# ==================== ADMIN COMMAND ====================
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin command"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ <b>ACCESS DENIED</b>\n\nThis command is for admins only.", parse_mode='HTML')
        return
    
    await admin_panel(update, context)

# ==================== MAIN FUNCTION ====================
def main():
    """Start the bot"""
    load_data()
    
    BOT_TOKEN = os.environ.get('BOT_TOKEN', '8264147086:AAGyV-FJ1Eaqu1q3ktMz70PLGx9CBG_kqYg')
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("redeem", redeem_command))
    application.add_handler(CallbackQueryHandler(verify_join_callback, pattern='^verify_join$'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    print("=" * 70)
    print("🤖 TRACKER PRO - ADMIN EDITION")
    print("=" * 70)
    print("✅ Features:")
    print("   • Admin Panel with full control")
    print("   • User Management (Ban/Unban)")
    print("   • Credit Management")
    print("   • Redeem Code System")
    print("   • 3 Search Services")
    print("   • Data Auto-save")
    print("=" * 70)
    print("⚠️ Set ADMIN_IDS in line 29 with your Telegram ID")
    print("=" * 70)
    print("🚀 Bot started successfully!")
    print("=" * 70)
    
    async def auto_save(context: ContextTypes.DEFAULT_TYPE):
        save_data()
    
    application.job_queue.run_repeating(auto_save, interval=300, first=10)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()