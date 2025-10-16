# =======================================================
# ©️ 2025-26 All Rights Reserved by Purvi Bots (Im-Notcoder) 🚀

# This source code is under MIT License 📜 Unauthorized forking, importing, or using this code without giving proper credit will result in legal action ⚠️
 
# 📩 DM for permission : @TheSigmaCoder
# =======================================================

import time, asyncio
import random
from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from youtubesearchpython.__future__ import VideosSearch

import config
from ZeeMusic import app
from ZeeMusic.misc import _boot_
from ZeeMusic.plugins.sudo.sudoers import sudoers_list
from ZeeMusic.utils.database import get_served_chats, get_served_users, get_sudoers
from ZeeMusic.utils import bot_sys_stats
from ZeeMusic.utils.database import (
    add_served_chat,
    add_served_user,
    blacklisted_chats,
    get_lang,
    is_banned_user,
    is_on_off,
)
from ZeeMusic.utils.decorators.language import LanguageStart
from ZeeMusic.utils.formatters import get_readable_time
from ZeeMusic.utils.inline import help_pannel, private_panel, start_panel
from config import BANNED_USERS
from strings import get_string

NEXIO = [
    "https://files.catbox.moe/x5lytj.jpg",
    "https://files.catbox.moe/psya34.jpg",
    "https://files.catbox.moe/leaexg.jpg",
    "https://files.catbox.moe/b0e4vk.jpg",
    "https://files.catbox.moe/1b1wap.jpg",
    "https://files.catbox.moe/ommjjk.jpg",
    "https://files.catbox.moe/onurxm.jpg",
    "https://files.catbox.moe/97v75k.jpg",
    "https://files.catbox.moe/t833zy.jpg",
    "https://files.catbox.moe/472piq.jpg",
    "https://files.catbox.moe/qwjeyk.jpg",
    "https://files.catbox.moe/t0hopv.jpg",
    "https://files.catbox.moe/u5ux0j.jpg",
    "https://files.catbox.moe/h1yk4w.jpg",
    "https://files.catbox.moe/gl5rg8.jpg",
]

PURVI_STKR = [
    "CAACAgUAAxkBAAIBO2i1Spi48ZdWCNehv-GklSI9aRYWAAJ9GAACXB-pVds_sm8brMEqHgQ",
    "CAACAgUAAxkBAAIBOmi1Sogwaoh01l5-e-lJkK1VNY6MAAIlGAACKI6wVVNEvN-6z3Z7HgQ",
    "CAACAgUAAxkBAAIBPGi1Spv1tlx90xM1Q7TRNyL0fhcJAAKDGgACZSupVbmJpWW9LmXJHgQ",
    "CAACAgUAAxkBAAIBPWi1SpxJZKxuWYsZ_G06j_G_9QGkAAIsHwACdd6xVd2HOWQPA_qtHgQ",
    "CAACAgUAAxkBAAIBPmi1Sp4QFoLkZ0oN3d01kZQOHQRwAAI4FwACDDexVVp91U_1BZKFHgQ",
    "CAACAgUAAxkBAAIBP2i1SqFoa4yqgl1QSISZrQ4VuYWgAAIpFQACvTqpVWqbFSKOnWYxHgQ",
    "CAACAgUAAxkBAAIBQGi1Sqk3OGQ2jRW2rN6ZVZ7vWY2ZAAJZHQACCa-pVfefqZZtTHEdHgQ",
]

EFFECT_IDS = [
    5046509860389126442,
    5107584321108051014,
    5104841245755180586,
    5159385139981059251,
]

emojis = ["🥰", "🔥", "💖", "😁", "😎", "🌚", "❤️‍🔥", "♥️", "🎉", "🙈"]

@app.on_message(filters.command(["start"]) & filters.private & ~BANNED_USERS)
@LanguageStart
async def start_pm(client, message: Message, _):
    print(f"🎯 START COMMAND RECEIVED FROM: {message.from_user.id} (@{message.from_user.username})")
    
    # Step 1: Add user to database
    try:
        await add_served_user(message.from_user.id)
        print("✅ User added to served users database")
    except Exception as e:
        print(f"❌ Database error: {e}")

    # Step 2: React to user's message
    try:
        selected_emoji = random.choice(emojis)
        print(f"🎭 Attempting to react with emoji: {selected_emoji}")
        await message.react(emoji=selected_emoji)
        print("✅ Reaction successful!")
    except Exception as e:
        print(f"❌ Reaction failed: {e}")
        # Alternative reaction method
        try:
            print("🔄 Trying alternative reaction method...")
            await client.send_reaction(
                chat_id=message.chat.id,
                message_id=message.id,
                emoji=random.choice(emojis)
            )
            print("✅ Alternative reaction successful!")
        except Exception as e2:
            print(f"❌ Alternative reaction also failed: {e2}")

    # Step 3: Send and delete sticker
    try:
        print("🎨 Sending sticker...")
        selected_sticker = random.choice(PURVI_STKR)
        sticker = await message.reply_sticker(sticker=selected_sticker)
        print("✅ Sticker sent successfully")
        
        await asyncio.sleep(1)
        await sticker.delete()
        print("✅ Sticker deleted successfully")
    except Exception as e:
        print(f"❌ Sticker error: {e}")

    # Step 4: Handle command arguments
    if len(message.text.split()) > 1:
        name = message.text.split(None, 1)[1]
        print(f"📦 Command argument: {name}")

        if name.startswith("help"):
            print("🆘 Help command detected")
            try:
                keyboard = help_pannel(_)
                await message.reply_photo(
                    random.choice(NEXIO),
                    message_effect_id=random.choice(EFFECT_IDS),
                    caption=_["help_1"].format(config.SUPPORT_CHAT),
                    reply_markup=keyboard,
                )
                print("✅ Help message sent")
            except Exception as e:
                print(f"❌ Help command error: {e}")

        elif name.startswith("sud"):
            print("👑 Sudo list command detected")
            try:
                await sudoers_list(client=client, message=message, _=_)
                if await is_on_off(2):
                    await app.send_message(
                        chat_id=config.LOGGER_ID,
                        text=f"{message.from_user.mention} ᴊᴜsᴛ sᴛᴀʀᴛᴇᴅ ᴛʜᴇ ʙᴏᴛ ᴛᴏ ᴄʜᴇᴄᴋ <b>sᴜᴅᴏʟɪsᴛ</b>.\n\n<b>ᴜsᴇʀ ɪᴅ :</b> <code>{message.from_user.id}</code>\n<b>ᴜsᴇʀɴᴀᴍᴇ :</b> @{message.from_user.username}",
                    )
                print("✅ Sudo list processed")
            except Exception as e:
                print(f"❌ Sudo list error: {e}")

        elif name.startswith("inf"):
            print("📊 Info command detected")
            try:
                m = await message.reply_text("🔎")
                query = (str(name)).replace("info_", "", 1)
                query = f"https://www.youtube.com/watch?v={query}"
                
                print(f"🔍 Searching YouTube for: {query}")
                results = VideosSearch(query, limit=1)
                search_results = await results.next()
                
                for result in search_results["result"]:
                    title = result["title"]
                    duration = result["duration"]
                    views = result["viewCount"]["short"]
                    thumbnail = result["thumbnails"][0]["url"].split("?")[0]
                    channellink = result["channel"]["link"]
                    channel = result["channel"]["name"]
                    link = result["link"]
                    published = result["publishedTime"]

                searched_text = _["start_6"].format(
                    title, duration, views, published, channellink, channel, app.mention
                )
                key = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(text=_["S_B_8"], url=link),
                            InlineKeyboardButton(text=_["S_B_9"], url=config.SUPPORT_CHAT),
                        ],
                    ]
                )
                await m.delete()
                await app.send_photo(
                    chat_id=message.chat.id,
                    photo=thumbnail,
                    message_effect_id=random.choice(EFFECT_IDS),
                    caption=searched_text,
                    reply_markup=key,
                )
                print("✅ Info message sent")
                
                if await is_on_off(2):
                    await app.send_message(
                        chat_id=config.LOGGER_ID,
                        text=f"{message.from_user.mention} ᴊᴜsᴛ sᴛᴀʀᴛᴇᴅ ᴛʜᴇ ʙᴏᴛ ᴛᴏ ᴄʜᴇᴄᴋ <b>ᴛʀᴀᴄᴋ ɪɴғᴏʀᴍᴀᴛɪᴏɴ</b>.\n\n<b>ᴜsᴇʀ ɪᴅ :</b> <code>{message.from_user.id}</code>\n<b>ᴜsᴇʀɴᴀᴍᴇ :</b> @{message.from_user.username}",
                    )
            except Exception as e:
                print(f"❌ Info command error: {e}")

    else:
        # Step 5: Normal start command without arguments
        print("🚀 Normal start command (no arguments)")
        try:
            purvi = await message.reply_text(f"**ʜєʟʟᴏ ᴅєᴧʀ {message.from_user.mention}**")
            await asyncio.sleep(0.4)
            await purvi.edit_text("**ɪ ᴧϻ ʏσᴜʀ ϻᴜsɪᴄ ʙσᴛ..🦋**")
            await asyncio.sleep(0.4)
            await purvi.edit_text("**ʜσᴡ ᴧʀє ʏσᴜ ᴛσᴅᴧʏ.....??**")
            await asyncio.sleep(0.4)
            await purvi.delete()
            print("✅ Animated text sequence completed")
        except Exception as e:
            print(f"❌ Animated text error: {e}")

        try:
            out = private_panel(_)
            await message.reply_photo(
                random.choice(NEXIO),
                message_effect_id=random.choice(EFFECT_IDS),
                caption=_["start_2"].format(message.from_user.mention, app.mention),
                reply_markup=InlineKeyboardMarkup(out),
            )
            print("✅ Welcome message with photo sent")
        except Exception as e:
            print(f"❌ Welcome message error: {e}")

        if await is_on_off(2):
            try:
                await app.send_message(
                    chat_id=config.LOGGER_ID,
                    text=f"{message.from_user.mention} ᴊᴜsᴛ sᴛᴀʀᴛᴇᴅ ᴛʜᴇ ʙᴏᴛ.\n\n<b>ᴜsᴇʀ ɪᴅ :</b> <code>{message.from_user.id}</code>\n<b>ᴜsᴇʀɴᴀᴍᴇ :</b> @{message.from_user.username}",
                )
                print("✅ Log message sent to logger")
            except Exception as e:
                print(f"❌ Logger error: {e}")

    print("🎊 Start command processing completed\n")

@app.on_message(filters.command(["start"]) & filters.group & ~BANNED_USERS)
@LanguageStart
async def start_gp(client, message: Message, _):
    print(f"👥 GROUP START COMMAND FROM: {message.chat.id} ({message.chat.title})")
    try:
        out = start_panel(_)
        uptime = int(time.time() - _boot_)
        await message.reply_photo(
            random.choice(NEXIO),
            caption=_["start_1"].format(app.mention, get_readable_time(uptime)),
            reply_markup=InlineKeyboardMarkup(out),
        )
        await add_served_chat(message.chat.id)
        print("✅ Group start command processed successfully")
    except Exception as e:
        print(f"❌ Group start error: {e}")

@app.on_message(filters.new_chat_members, group=-1)
async def welcome(client, message: Message):
    print(f"🆕 NEW CHAT MEMBER DETECTED IN: {message.chat.id}")
    for member in message.new_chat_members:
        try:
            language = await get_lang(message.chat.id)
            _ = get_string(language)
            
            if await is_banned_user(member.id):
                try:
                    await message.chat.ban_member(member.id)
                    print(f"🚫 Banned user {member.id} kicked from group")
                except Exception as e:
                    print(f"❌ Ban enforcement error: {e}")
                    
            if member.id == app.id:
                print("🤖 Bot added to new group")
                if message.chat.type != ChatType.SUPERGROUP:
                    await message.reply_text(_["start_4"])
                    await app.leave_chat(message.chat.id)
                    print("❌ Left non-supergroup")
                    return
                    
                if message.chat.id in await blacklisted_chats():
                    await message.reply_text(
                        _["start_5"].format(
                            app.mention,
                            f"https://t.me/{app.username}?start=sudolist",
                            config.SUPPORT_CHAT,
                        ),
                        disable_web_page_preview=True,
                    )
                    await app.leave_chat(message.chat.id)
                    print("❌ Left blacklisted chat")
                    return

                out = start_panel(_)
                await message.reply_photo(
                    random.choice(NEXIO),
                    caption=_["start_3"].format(
                        message.from_user.mention,
                        app.mention,
                        message.chat.title,
                        app.mention,
                    ),
                    reply_markup=InlineKeyboardMarkup(out),
                )
                await add_served_chat(message.chat.id)
                print("✅ Bot welcome message sent in group")
                await message.stop_propagation()
                
        except Exception as ex:
            print(f"❌ Welcome handler error: {ex}")

# ======================================================
# ©️ 2025-26 All Rights Reserved by Purvi Bots (Im-Notcoder) 😎

# 🧑‍💻 Developer : t.me/TheSigmaCoder
# 🔗 Source link : GitHub.com/Im-Notcoder/Sonali-MusicV2
# 📢 Telegram channel : t.me/Purvi_Bots
# =======================================================
