import os, asyncio, logging
from typing import Dict
from telegram import Update, Chat, User, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import MessageHandler, filters, ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from game.game import Game
from game.roles import *

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("werewolf-bot")

GAMES: Dict[int, Game] = {}
CHAOS_DECK = ALL_ROLES


# ==== Guards and helpers for pinning, roles, and votes ====
HOWTO_PINNED_CHATS = set()
PENDING_DM = {}  # chat_id -> set(user_ids) who have not opened DM
VOTE_MSG_IDS = {}  # chat_id -> message_id
BOT_USERNAME_CACHE = None

async def get_bot_username(ctx):
    global BOT_USERNAME_CACHE
    if BOT_USERNAME_CACHE:
        return BOT_USERNAME_CACHE
    try:
        me = await ctx.bot.get_me()
        BOT_USERNAME_CACHE = me.username
        return BOT_USERNAME_CACHE
    except Exception:
        return None

async def pin_howto_once(update, ctx):
    chat = update.effective_chat
    if not chat:
        return
    if chat.id in HOWTO_PINNED_CHATS:
        return
    # call howtoplay and pin the returned message if possible
    try:
        msg = await cmd_howtoplay(update, ctx)
        if hasattr(msg, "message_id"):
            try:
                await ctx.bot.pin_chat_message(chat_id=chat.id, message_id=msg.message_id)
            except Exception:
                pass
    except Exception:
        # ignore, do not break game flow
        pass
    HOWTO_PINNED_CHATS.add(chat.id)

async def build_open_dm_text_and_keyboard(chat_id: int, ctx):
    username = await get_bot_username(ctx)
    if not username:
        return "Buka DM bot dan tekan Start untuk terima role.", None
    deep = f"https://t.me/{username}?start=role_{chat_id}"
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔒 Open DM to get your role", url=deep)]])
    return "Belum buka DM dengan bot, tekan butang ini untuk terima role anda.", kb

async def send_roles_for_chat(chat_id: int, ctx):
    # send DM roles to all players in this chat game
    game = GAMES.get(chat_id)
    if not game:
        return
    pending = set()
    mason_names = [game.players[m].name for m in getattr(game, "masons", [])] if getattr(game, "masons", None) else []
    for pid, p in game.players.items():
        try:
            text = f"Role kau, {p.role.name}."
            role_tip = {
                "Werewolf":"Bunuh seorang setiap malam, guna Kill dalam DM",
                "Wolf Cub":"Bunuh seorang setiap malam, guna Kill",
                "Lone wolf":"Bunuh seorang setiap malam, guna Kill",
                "Seer":"Intai seorang setiap malam, guna Peek",
                "Aura Seer":"Intai aura, guna Aura",
                "Bodyguard":"Lindung seorang, guna Protect, tidak boleh target sama 2 malam berturut-turut",
                "Doctor":"Selamatkan seorang, guna Save",
                "Witch":"Ada Heal sekali dan Poison sekali",
                "Priest":"Bless seorang, guna Bless",
                "Sorceress":"Scry seorang, cari Seer",
                "Vampire":"Gigit seorang, recruit team",
                "Cult Leader":"Recruit seorang masuk cult",
            }.get(p.role.name, "Fokus siang, undi bijak, hidupkan kampung")
            text += f" {role_tip}."
            # teammates
            if p.role.name in ["Werewolf","Wolf Cub","Lone wolf"]:
                pack = [game.players[w].name for w in getattr(game, "wolves", []) if w != pid]
                if pack:
                    text += " Wolf team, " + ", ".join(pack) + "."
            if p.role.name == "Mason" and mason_names:
                buddies = [n for n in mason_names if n != p.name]
                if buddies:
                    text += " Fellow Masons, " + ", ".join(buddies) + "."
            text += "\\n\\n📩 Guna butang di DM, bukan di group."
            await ctx.bot.send_message(chat_id=pid, text=text)
            # quick targets
            action_map = {
                "Seer":"peek","Aura Seer":"aura","Doctor":"save","Bodyguard":"protect",
                "Witch":"heal","Priest":"bless","Sorceress":"scry","Vampire":"bite",
                "Cult Leader":"recruit","Werewolf":"kill","Wolf Cub":"kill","Lone wolf":"kill"
            }
            if p.role.name in action_map:
                await ctx.bot.send_message(chat_id=pid, text="Quick targets", reply_markup=targets_keyboard(game, action_map[p.role.name]))
        except Exception as e:
            # most likely Forbidden, user never started the bot
            pending.add(pid)
    if pending:
        PENDING_DM[chat_id] = pending
        txt, kb = await build_open_dm_text_and_keyboard(chat_id, ctx)
        try:
            await ctx.bot.send_message(chat_id=chat_id, text=txt, reply_markup=kb)
        except Exception:
            pass

async def handle_start_deeplink(update, ctx):
    # Handles /start role_<chatid> from deep link, then sends that user's role
    msg = update.effective_message
    text = msg.text or ""
    if not text.startswith("/start"):
        return
    parts = text.split(maxsplit=1)
    payload = parts[1] if len(parts) > 1 else ""
    if not payload.startswith("role_"):
        return
    try:
        chat_id = int(payload.split("_",1)[1])
    except Exception:
        return
    game = GAMES.get(chat_id)
    if not game:
        await msg.reply_text("Tiada game aktif untuk chat ini.")
        return
    # send role now if exists
    p = game.players.get(update.effective_user.id)
    if not p:
        await msg.reply_text("Anda bukan pemain dalam game ini.")
        return
    try:
        await ctx.bot.send_message(chat_id=update.effective_user.id, text=f"Role kau, {p.role.name}.")
        # optional targets
        action_map = {"Seer":"peek","Aura Seer":"aura","Doctor":"save","Bodyguard":"protect","Witch":"heal","Priest":"bless","Sorceress":"scry","Vampire":"bite","Cult Leader":"recruit","Werewolf":"kill","Wolf Cub":"kill","Lone wolf":"kill"}
        if p.role.name in action_map:
            await ctx.bot.send_message(chat_id=update.effective_user.id, text="Quick targets", reply_markup=targets_keyboard(game, action_map[p.role.name]))
        # remove from pending
        s = PENDING_DM.get(chat_id, set())
        if update.effective_user.id in s:
            s.discard(update.effective_user.id)
            PENDING_DM[chat_id] = s
    except Exception:
        pass

async def post_vote_keyboard(chat_id: int, ctx):
    # edit existing vote message if present, else post a new one
    game = GAMES.get(chat_id)
    if not game:
        return
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    rows = []
    alive = [p for p in game.players.values() if p.alive]
    # build buttons two per row
    row = []
    for i, p in enumerate(alive, start=1):
        row.append(InlineKeyboardButton(f"{i}, {p.name}", callback_data=f"vote:{p.user_id}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    # Day 1 include skip
    if getattr(game, "day_count", 1) == 1:
        rows.append([InlineKeyboardButton("↘ Skip lynch", callback_data="vote:0")])
    kb = InlineKeyboardMarkup(rows) if rows else None
    # post or edit
    msg_id = VOTE_MSG_IDS.get(chat_id)
    text = "🗳 Vote sekarang, tekan nama di bawah."
    try:
        if msg_id:
            await ctx.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, reply_markup=kb)
        else:
            m = await ctx.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)
            VOTE_MSG_IDS[chat_id] = m.message_id
    except Exception:
        # fallback to sending fresh
        try:
            m = await ctx.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)
            VOTE_MSG_IDS[chat_id] = m.message_id
        except Exception:
            pass

async def cmd_resendroles(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.id not in GAMES:
        await update.effective_message.reply_text("Tiada game aktif di sini.")
        return
    game = GAMES[chat.id]
    if user.id != game.host_id:
        await update.effective_message.reply_text("Host sahaja boleh guna arahan ini.")
        return
    await send_roles_for_chat(chat.id, ctx)
    pending = PENDING_DM.get(chat.id, set())
    if pending:
        await update.effective_message.reply_text(f"Masih belum buka DM, {len(pending)} pemain.")
    else:
        await update.effective_message.reply_text("Semua role telah dihantar di DM.")


def nextphase_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("➡ Next Phase", callback_data=f"nextphase:{chat_id}")]])

async def handle_nextphase_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat_id = None
    try:
        _, cid = (q.data or "").split(":")
        chat_id = int(cid)
    except Exception:
        return
    game = GAMES.get(chat_id)
    if not game:
        try:
            await q.edit_message_text("No active game here.")
        except Exception:
            pass
        return
    if q.from_user.id != game.host_id:
        try:
            await q.edit_message_text("Only the host can change the phase.")
        except Exception:
            pass
        return
    # If night, resolve and announce day, if day, end day to night
    if game.phase == "night":
        res = game.resolve_night()
        winner = game.is_over()
        text = res + (f" {winner}." if winner else "")
        try:
            await q.edit_message_text("Proceeding to day.")
        except Exception:
            pass
        await ctx.bot.send_message(chat_id=chat_id, text=text)
        if game.phase != "over":
            await ctx.bot.send_message(chat_id=chat_id, text="🌞 Day begins, discuss and vote.")
            await ctx.bot.send_message(chat_id=chat_id, text=send_vote_keyboard_text(game), reply_markup=vote_keyboard(game))
    elif game.phase == "day":
        res = game.end_day()
        try:
            await q.edit_message_text("Proceeding to night.")
        except Exception:
            pass
        await ctx.bot.send_message(chat_id=chat_id, text=res)
        if game.phase != "over" and game.phase == "night":
            await ctx.bot.send_message(chat_id=chat_id, text="🌙 Night begins, night roles act in DM.")
    else:
        try:
            await q.edit_message_text("Game belum bermula atau sudah tamat.")
        except Exception:
            pass


ROLE_EMOJI = {
    "Seer": "🔮",
    "Apprentice Seer": "🧑‍🔮",
    "Aura Seer": "✨🔮",
    "Bodyguard": "🛡",
    "Cult Leader": "✝️",
    "Cupid": "💘",
    "Cursed": "😈",
    "Diseased": "🤒",
    "Doppleganger": "🪞",
    "Drunk": "🍺",
    "Ghost": "👻",
    "Hoodlum": "😎",
    "Hunter": "🎯",
    "Lone wolf": "🐺",
    "Lycan": "🐺🌕",
    "Mason": "🧱",
    "Mayor": "🎩",
    "Minion": "🤏😈",
    "Old Hag": "👵",
    "Paranormal Investigator": "🕵️‍♂️👻",
    "Pacifist": "✌️",
    "Priest": "✝️🕊",
    "Prince": "👑",
    "Sorceress": "🧙‍♀️",
    "Spellcaster": "🪄",
    "Tanner": "🧥",
    "Tough Guy": "💪",
    "Troublemaker": "🌀",
    "Vampire": "🦇",
    "Village Idiot": "🤪",
    "Villager": "🏡",
    "Werewolf": "🐺",
    "Witch": "🧹",
    "Wolf Cub": "🐺🐾"
}
def role_emoji(name: str) -> str:
    return ROLE_EMOJI.get(name, "🎭")

AUTO_TASKS: Dict[int, asyncio.Task] = {}

def cancel_autoday(chat_id: int):
    t = AUTO_TASKS.get(chat_id)
    if t and not t.cancelled():
        t.cancel()
    AUTO_TASKS.pop(chat_id, None)

async def schedule_autoday(chat_id: int, ctx: ContextTypes.DEFAULT_TYPE, delay_secs: int = 45):
    cancel_autoday(chat_id)
    async def _go():
        try:
            await asyncio.sleep(delay_secs)
            game = GAMES.get(chat_id)
            if not game or game.phase != "night":
                return
            res = game.resolve_night()
            winner = game.is_over()
            text = res + (f" {winner}." if winner else "")
            await ctx.bot.send_message(chat_id=chat_id, text=text)
            if game.phase != "over":
                await ctx.bot.send_message(chat_id=chat_id, text="Day phase. Use, /vote <name or number>. Host can /tally and /endday.")
        except asyncio.CancelledError:
            return
    AUTO_TASKS[chat_id] = asyncio.create_task(_go())

def proceed_button(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Proceed to Day", callback_data=f"proceed_day:{chat_id}")]])

def mention(u: User) -> str:
    return f"@{u.username}" if u.username else u.full_name

def numbered_alive_list(game: Game) -> str:
    alive = sorted([p for p in game.players.values() if p.alive], key=lambda x: x.name.lower())
    if not alive:
        return "No living players."
    return "\n".join(f"{i+1}. {p.name}" for i, p in enumerate(alive))

def group_keyboard(is_host: bool) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton("/join"), KeyboardButton("/status"), KeyboardButton("/listalive")]]
    if is_host:
        rows.append([KeyboardButton("/startgame"), KeyboardButton("/tally"), KeyboardButton("/endday")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, selective=True)

def targets_keyboard(game: Game, action: str) -> InlineKeyboardMarkup:
    alive = sorted([p for p in game.players.values() if p.alive], key=lambda x: x.name.lower())
    buttons = [[InlineKeyboardButton(f"{i+1}. {p.name}", callback_data=f"{action}:{p.user_id}")] for i, p in enumerate(alive)]
    return InlineKeyboardMarkup(buttons)

def send_vote_keyboard_text(game: Game) -> str:
    return "🗳 Vote sekarang, pilih nama di bawah, Day " + str(game.day_count)

def vote_keyboard(game: Game) -> InlineKeyboardMarkup:
    alive = sorted([p for p in game.players.values() if p.alive], key=lambda x: x.name.lower())
    rows = [[InlineKeyboardButton(f"{i+1}. {p.name}", callback_data=f"vote:{p.user_id}")] for i, p in enumerate(alive)]
    if game.day_count == 1:
        rows.append([InlineKeyboardButton("⏭ Skip lynch", callback_data="vote:skip")])
    return InlineKeyboardMarkup(rows)

def build_modboard_text(game: Game) -> str:
    lines = ["🛠 Moderator Board"]
    for i, p in enumerate(game.players.values(), start=1):
        role_name = p.role.name if p.role else "Unassigned"
        emoji = role_emoji(role_name)
        status = "Alive" if p.alive else "Dead"
        cult_tag = " , Cult" if p.user_id in game.cult else ""
        lines.append(f"{i}. {p.name} , {emoji} {role_name}{cult_tag} , {status}")
    return "\n".join(lines)

async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("Pong, bot is online.")

async def cmd_howtoplay(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    parts = [
        "🐺 Selamat datang ke Werewolf Chaos Deck, semua role sekali, mission, survive, tipu orang, conquer kampung, have fun, jangan bocor role.",
        "📊 Player count, nak game lit, kena cukup player, min 8, best 12 hingga 20, max 24 untuk fun, 30 ke atas kalau kau memang nak chaos.",
        "🔁 Game flow, siang, sembang, tuduh, vote, malam, role special jalan kerja dalam DM, bunuh, protect, intip, recruit, ulang sampai ada pemenang.",
        "🧭 Main di group, guna button bawah chat, /join untuk masuk, /status untuk tengok pemain, /listalive untuk yang hidup, host guna /startgame, /tally, /endday, /modboard.",
        "🎯 DM actions, kalau ada role, boleh taip command atau guna butang sasaran, /kill, /peek, /aura, /save, /protect, /heal, /poison, /bless, /scry, /bite, /recruit.",
        "💡 Tips, check DM waktu malam, guna nombor dari /listalive untuk sasaran cepat, act natural kalau jahat, trust no one, trust the bot."
    ]
    sent0 = await update.effective_message.reply_text(parts[0])
    try:
        await sent0.pin()
    except Exception as e:
        log.info("Pin failed, %s", e)
    await asyncio.sleep(0.5)
    for txt in parts[1:]:
        await update.effective_chat.send_message(txt)
        await asyncio.sleep(0.3)

async def cmd_modboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    game = None
    if chat and chat.id in GAMES and user.id == GAMES[chat.id].host_id:
        game = GAMES[chat.id]
    else:
        for g in GAMES.values():
            if g.host_id == user.id:
                game = g
                break
    if game is None:
        await update.effective_message.reply_text("You are not a host in any active game.")
        return
    if user.id != game.host_id:
        await update.effective_message.reply_text("Only the host can view the moderator board.")
        return
    text = build_modboard_text(game)
    if chat and chat.type != Chat.PRIVATE:
        try:
            await ctx.bot.send_message(chat_id=user.id, text=text)
            await update.effective_message.reply_text("I sent the moderator board to your DM.")
        except Exception:
            await update.effective_message.reply_text("I could not DM you, start a private chat with me first, then run /modboard again.")
    else:
        await update.effective_message.reply_text(text)

async def cmd_cheatroles(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    game = None
    if chat and chat.id in GAMES and GAMES[chat.id].host_id == user.id:
        game = GAMES[chat.id]
    else:
        for g in GAMES.values():
            if g.host_id == user.id:
                game = g
                break
    if not game:
        await update.effective_message.reply_text("You are not a host in any active game.")
        return
    lines = ["🎭 Cheat Roles Board , Host Only", "Ssshhh jangan bagitau orang lain 👀", ""]
    if not game.players:
        lines.append("No players yet.")
    else:
        for i, p in enumerate(game.players.values(), start=1):
            role_name = p.role.name if p.role else "Unassigned"
            emoji = role_emoji(role_name)
            lines.append(f"{i}. {p.name} , {emoji} {role_name}")
    msg = "\n".join(lines)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔒 Close", callback_data="close_message")]])
    if chat and chat.type != Chat.PRIVATE:
        try:
            await ctx.bot.send_message(chat_id=user.id, text=msg, reply_markup=kb)
            await update.effective_message.reply_text("I sent the cheat board to your DM.")
        except Exception:
            await update.effective_message.reply_text("I could not DM you, start a private chat with me first, then run /cheatroles again.")
    else:
        await update.effective_message.reply_text(msg, reply_markup=kb)

async def close_message_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.message.delete()
    except Exception:
        pass
    await q.answer()

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    game = GAMES.get(chat.id) if chat and chat.id in GAMES else next((g for g in GAMES.values() if user.id in g.players), None)
    if not game:
        await update.effective_message.reply_text("No active game here.")
        return
    phase = game.phase
    day = game.day_count
    last = game.name_of(game.last_killed) if game.last_killed else "None"
    alive_names = [p.name for p in game.players.values() if p.alive]
    await update.effective_message.reply_text(f"📊 Status, phase, {phase}, day, {day}, last out, {last}. Alive, {len(alive_names)}.")

async def cmd_votes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active game here.")
        return
    game = GAMES[chat.id]
    if game.phase != "day":
        await update.effective_message.reply_text("It is not day.")
        return
    done, total = game.votes_progress()
    await update.effective_message.reply_text(f"🗳 Progres undi, {done} dari {total} siap. Guna /tally untuk kiraan.")


async def cmd_pending(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active game here.")
        return
    game = GAMES[chat.id]
    is_host = (user.id == game.host_id)
    items = game.pending_summary() if hasattr(game, "pending_summary") else ["No pending info."]
    txt = "⏳ Pending" + "".join(items)
    if is_host:
        try:
            await update.effective_message.reply_text(txt, reply_markup=nextphase_keyboard(chat.id))
        except Exception:
            await update.effective_message.reply_text(txt)
    else:
        await update.effective_message.reply_text(txt)
    return

    game = GAMES[chat.id]
    if user.id != game.host_id:
        await update.effective_message.reply_text("Only the host can view pending actions.")
        return
    items = game.pending_summary()
    await update.effective_message.reply_text("⏳ Pending" + "".join(items))

async def cmd_newgame(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.type == Chat.PRIVATE:
        await update.effective_message.reply_text("Use /newgame in a group chat.")
    await pin_howto_once(update, ctx)
    return
    GAMES[chat.id] = Game(chat_id=chat.id, host_id=user.id)
    await update.effective_message.reply_text(
        "New Werewolf lobby created. Preset, Chaos Deck, all roles included. Players use /join. Host uses /startgame when ready.",
        reply_markup=group_keyboard(is_host=True)
    )

    # Auto howtoplay with pin
    try:
        await cmd_howtoplay(update, ctx)
    except Exception:
        pass

async def cmd_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active lobby. Use /newgame first.")
        return
    game = GAMES[chat.id]
    res = game.add_player(user.id, mention(user))
    await update.effective_message.reply_text(res, reply_markup=group_keyboard(is_host=(game.host_id == user.id)))


async def cmd_votebuttons(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active game here.")
        return
    game = GAMES[chat.id]
    if game.phase != "day":
        await update.effective_message.reply_text("It is not day.")
        return
    await update.effective_message.reply_text(send_vote_keyboard_text(game), reply_markup=vote_keyboard(game))
async def cmd_listalive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    game = GAMES.get(chat.id) if chat and chat.id in GAMES else None
    if not game:
        await update.effective_message.reply_text("No active game here.")
        return
    await update.effective_message.reply_text("Alive\n" + numbered_alive_list(game))

async def cmd_showroles(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No lobby here.")
        return
    names = [r.name for r in CHAOS_DECK]
    await update.effective_message.reply_text("Current roles\n" + ", ".join(names))

async def cmd_mayor(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active game here.")
        return
    game = GAMES[chat.id]
    p = game.players.get(user.id)
    if not p or not p.alive or p.role is not MAYOR:
        await update.effective_message.reply_text("Only the Mayor can use this.")
        return
    if game.mayor_revealed:
        await update.effective_message.reply_text("Mayor is already revealed.")
        return
    game.mayor_revealed = user.id
    await update.effective_message.reply_text(f"{p.name} reveals as Mayor. Their vote counts double.")

async def cmd_startgame(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active lobby. Use /newgame first.")
        return
    game = GAMES[chat.id]
    if user.id != game.host_id:
        await update.effective_message.reply_text("Only the host can start the game.")
        return

    # minimum players check
    if len(game.players) < 5:
        await update.effective_message.reply_text("⚠ Minimum 5 players diperlukan, jom ajak kawan lagi, at least 5.")
        return
    roleset = CHAOS_DECK
    res = game.assign_roles(roleset)
    await update.effective_message.reply_text(res)
    # Announce Day 1
    await update.effective_message.reply_text("🌞 Siang 1 bermula, masa borak dan undi. Gunakan butang undi di bawah atau /votebuttons.")
    try:
        await cmd_votebuttons(update, ctx)
    except Exception:
        pass
    if game.phase == "day":
            await update.effective_message.reply_text("🌞 Siang 1 bermula, masa borak, tuduh, dan undi.")
            await update.effective_message.reply_text(send_vote_keyboard_text(game), reply_markup=vote_keyboard(game))
            # DM teammates info once on Day 1
            try:
                for pid, p in game.players.items():
                    packs = teammates_for(pid, game)
                    if packs:
                        lines = ["🤝 Teammates"]
                        for label, names in packs.items():
                            filtered = [n for n in names if n != p.name]
                            if not filtered:
                                continue
                            lines.append(f"{label}, " + ", ".join(filtered))
                        if len(lines) > 1:
                            await ctx.bot.send_message(chat_id=pid, text="\n".join(lines))
            except Exception as e:
                log.info("Teammate DM failed, %s", e)
            try:
                await cmd_howtoplay(update, ctx)
            except Exception as e:
                log.info("Auto howtoplay failed, %s", e)
    elif game.phase == "night":
            await update.effective_message.reply_text(f"Starting game with Chaos Deck. Players, {len(game.players)}. Assigning roles from the full deck.")
            mason_names = [game.players[m].name for m in game.masons]
            for pid, p in game.players.items():
                try:
                    text = f"Your role is {p.role.name}. You are {'Alive' if p.alive else 'Dead'}."
                    if p.role in (WEREWOLF, WOLF_CUB, LONE_WOLF):
                        pack = [game.players[w].name for w in game.wolves]
                        text += " Wolf team, " + ", ".join(pack)
                        text += " Use, /kill <name or number> at night."
                    if p.role is SEER:
                        text += " Use, /peek <name or number>."
                    if p.role is AURA_SEER:
                        text += " Use, /aura <name or number>."
                    if p.role is DOCTOR:
                        text += " Use, /save <name or number>."
                    if p.role is BODYGUARD:
                        text += " Use, /protect <name or number>. You cannot protect the same target twice."
                    if p.role is WITCH:
                        text += " You have two potions, heal once and poison once. /heal, /poison."
                    if p.role is OLD_HAG:
                        text += " You can silence one player, /silence <target>."
                    if p.role is SORCERESS:
                        text += " You can scry a Seer type, /scry <target>."
                    if p.role is PRIEST:
                        text += " You can bless one player, /bless <target>."
                    if p.role is VAMPIRE:
                        text += " You can bite one target, /bite <target>."
                    if p.role is CULT_LEADER:
                        text += " You can recruit one target, /recruit <target>."
                    if p.role is MASON and mason_names:
                        text += " Your fellow Masons, " + ", ".join(n for n in mason_names if n != p.name)
                    await ctx.bot.send_message(chat_id=pid, text=text + "\n\n📩 Tip, guna butang ini dalam DM, bukan dalam group.")
                    if p.role in (WEREWOLF, WOLF_CUB, LONE_WOLF, SEER, AURA_SEER, DOCTOR, BODYGUARD, WITCH, PRIEST, SORCERESS, VAMPIRE, CULT_LEADER):
                        action_map = {SEER:"peek", AURA_SEER:"aura", DOCTOR:"save", BODYGUARD:"protect", WITCH:"heal", PRIEST:"bless", SORCERESS:"scry", VAMPIRE:"bite", CULT_LEADER:"recruit", WEREWOLF:"kill", WOLF_CUB:"kill", LONE_WOLF:"kill"}
                        await ctx.bot.send_message(chat_id=pid, text="Quick targets", reply_markup=targets_keyboard(game, action_map[p.role]))
                except Exception as e:
                    log.warning("Failed to DM player %s, %s", p.name, e)
            await update.effective_message.reply_text("🌞 Siang 1 bermula, check DM untuk aksi. Aku akan pin cara main untuk semua.")
            try:
                await cmd_howtoplay(update, ctx)
            except Exception as e:
                log.info("Auto howtoplay failed, %s", e)

async def cmd_day(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active game here.")
        return
    game = GAMES[chat.id]
    if game.phase != "night":
        await update.effective_message.reply_text("It is not night.")
        return
    cancel_autoday(chat.id)
    res = game.resolve_night()
    winner = game.is_over()
    await update.effective_message.reply_text(res + (f" {winner}." if winner else ""))
    if game.phase == "over":
        return
    await update.effective_message.reply_text("Day phase. Use, /vote <name or number>. Host can /tally and /endday.")
    try:
        await update.effective_chat.send_message("🗳 Vote sekarang, pilih nama bawah", reply_markup=targets_keyboard(game, "vote"))
    except Exception as e:
        log.info("Vote keyboard failed, %s", e)

async def cmd_vote(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active game here.")
        return
    game = GAMES[chat.id]
    if game.phase != "day":
        await update.effective_message.reply_text("It is not day.")
        return
    if not ctx.args:
        await update.effective_message.reply_text("Usage, /vote name, or /vote number, try /listalive")
        return
    token = " ".join(ctx.args)
    target_id = game.resolve_target(token, alive_only=True)
    if target_id is None:
        await update.effective_message.reply_text("No unique match, try /listalive then use a number.")
        return
    res = game.vote(user.id, target_id)
    await update.effective_message.reply_text(res)

async def cmd_tally(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active game here.")
        return
    game = GAMES[chat.id]
    t = game.tally()
    if not t:
        await update.effective_message.reply_text("🗳 Belum ada undian.")
        return
    lines = [f"{game.name_of(pid)}: {count}" for pid, count in t.items()]
    await update.effective_message.reply_text("🧮 Kiraan undi\n" + "\n".join(lines))

async def cmd_endday(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active game here.")
        return
    game = GAMES[chat.id]
    cancel_autoday(chat.id)
    res = game.end_day()
    await update.effective_message.reply_text(res)
    if game.phase == "over":
        return
    if game.phase == "day":
        await update.effective_message.reply_text("🌞 Siang 1 bermula, masa borak, tuduh, dan undi. Guna /vote <nama atau nombor>, tengok senarai dengan /listalive.")
        # Post vote buttons for quick voting
        try:
            await update.effective_chat.send_message("🗳 Vote sekarang, pilih nama bawah", reply_markup=targets_keyboard(game, "vote"))
        except Exception as e:
            log.info("Vote keyboard failed, %s", e)

        # DM teammates info once on Day 1
        try:
            for pid, p in game.players.items():
                packs = teammates_for(pid, game)
                if packs:
                    lines = ["🤝 Teammates"]
                    for label, names in packs.items():
                        filtered = [n for n in names if n != p.name]
                        if not filtered:
                            continue
                        lines.append(f"{label}, " + ", ".join(filtered))
                    if len(lines) > 1:
                        await ctx.bot.send_message(chat_id=pid, text="\n".join(lines))
        except Exception as e:
            log.info("Teammate DM failed, %s", e)
        try:
            await cmd_howtoplay(update, ctx)
        except Exception as e:
            log.info("Auto howtoplay failed, %s", e)
    
    elif game.phase == "night":
        await update.effective_message.reply_text("Night phase. Night roles, act in DM.")


async def handle_action_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    try:
        action, target_str = data.split(":")
        target_id = int(target_str)
    except Exception:
        try:
            await q.edit_message_text("Button data error, try again in DM.")
        except Exception:
            pass
        return

    user = q.from_user
    game = next((g for g in GAMES.values() if user.id in g.players), None)
    if game is None:
        try:
            await q.edit_message_text("No active game for you. Use buttons in DM only.")
        except Exception:
            pass
        return

    mapping = {"kill":"wolf_vote","peek":"seer_peek","aura":"aura_peek","save":"doctor_save","protect":"bodyguard_protect","heal":"witch_heal","poison":"witch_poison","bless":"priest_bless","scry":"sorceress_scry","bite":"vampire_bite","recruit":"cult_recruit","vote":"vote"}
    cmd_from_action = {
        "kill": "/kill",
        "peek": "/peek",
        "aura": "/aura",
        "save": "/save",
        "protect": "/protect",
        "heal": "/heal",
        "poison": "/poison",
        "bless": "/bless",
        "scry": "/scry",
        "bite": "/bite",
        "recruit": "/recruit",
    }

    method_name = mapping.get(action)
    if not method_name or not hasattr(game, method_name):
        # Fallback, show a copyable command and re-send target buttons
        cmd = cmd_from_action.get(action, "/help")
        try:
            await q.edit_message_text(f"Action not supported here. DM only. Copy and send, {cmd} {target_id}", reply_markup=targets_keyboard(game, action))
        except Exception:
            await ctx.bot.send_message(chat_id=user.id, text=f"Action not supported here. DM only. Copy and send, {cmd} {target_id}", reply_markup=targets_keyboard(game, action))
        return

    # Call the game method
    try:
        res = getattr(game, method_name)(user.id, target_id)
    except Exception as e:
        # Fallback to manual command if method raised
        cmd = cmd_from_action.get(action, "/help")
        try:
            await q.edit_message_text(f"Action error, try command, {cmd} {target_id}")
        except Exception:
            await ctx.bot.send_message(chat_id=user.id, text=f"Action error, try command, {cmd} {target_id}")
        return

    # Show result
    try:
        await q.edit_message_text(f"{res}")
    except Exception:
        await ctx.bot.send_message(chat_id=user.id, text=res)
    return

    user = q.from_user
    game = next((g for g in GAMES.values() if user.id in g.players), None)
    if game is None:
        await q.edit_message_text("You are not in a game.")
        return
    mapping = {"kill":"wolf_vote","peek":"seer_peek","aura":"aura_peek","save":"doctor_save","protect":"bodyguard_protect","heal":"witch_heal","poison":"witch_poison","bless":"priest_bless","scry":"sorceress_scry","bite":"vampire_bite","recruit":"cult_recruit","vote":"vote"}
    if not hasattr(game, mapping.get(action, "")):
        await q.edit_message_text("Action not supported.")
        return
    res = getattr(game, mapping[action])(user.id, target_id)
    try:
        await q.edit_message_text(f"{res}")
    except Exception:
        await ctx.bot.send_message(chat_id=user.id, text=res)

async def handle_vote_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    user = q.from_user
    # try resolve game by chat or membership
    chat = update.effective_chat
    game = None
    if chat and chat.id in GAMES:
        game = GAMES[chat.id]
    else:
        for g in GAMES.values():
            if user.id in g.players:
                game = g
                break
    if not game:
        try:
            await q.edit_message_text("No active game here.")
        except Exception:
            pass
        return
    if game.phase != "day":
        try:
            await q.edit_message_text("It is not day.")
        except Exception:
            pass
        return
    target_id = -1 if data.endswith(":skip") else int(data.split(":")[1])
    res = game.vote(user.id, target_id)
    try:
        await q.edit_message_text(res)
    except Exception:
        await ctx.bot.send_message(chat_id=user.id, text=res)

async def _single_target_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE, action: str, method_name: str, alive_only=True):
    user = update.effective_user
    if update.effective_chat is None or update.effective_chat.type != Chat.PRIVATE:
        return
    game = next((g for g in GAMES.values() if user.id in g.players), None)
    if game is None:
        await update.effective_message.reply_text("You are not in a game.")
        return
    if not ctx.args:
        await update.effective_message.reply_text("Pick a target", reply_markup=targets_keyboard(game, action))
        return
    target_id = game.resolve_target(" ".join(ctx.args), alive_only=alive_only)
    if target_id is None:
        await update.effective_message.reply_text("No unique match.")
        return
    res = getattr(game, method_name)(user.id, target_id)
    await update.effective_message.reply_text(res)

async def cmd_kill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):   await _single_target_cmd(update, ctx, "kill", "wolf_vote")
async def cmd_peek(update: Update, ctx: ContextTypes.DEFAULT_TYPE):   await _single_target_cmd(update, ctx, "peek", "seer_peek")
async def cmd_aura(update: Update, ctx: ContextTypes.DEFAULT_TYPE):   await _single_target_cmd(update, ctx, "aura", "aura_peek")
async def cmd_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):   await _single_target_cmd(update, ctx, "save", "doctor_save")
async def cmd_protect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):await _single_target_cmd(update, ctx, "protect", "bodyguard_protect")
async def cmd_heal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):   await _single_target_cmd(update, ctx, "heal", "witch_heal", alive_only=False)
async def cmd_poison(update: Update, ctx: ContextTypes.DEFAULT_TYPE): await _single_target_cmd(update, ctx, "poison", "witch_poison")
async def cmd_bless(update: Update, ctx: ContextTypes.DEFAULT_TYPE):  await _single_target_cmd(update, ctx, "bless", "priest_bless")
async def cmd_scry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):   await _single_target_cmd(update, ctx, "scry", "sorceress_scry")
async def cmd_bite(update: Update, ctx: ContextTypes.DEFAULT_TYPE):   await _single_target_cmd(update, ctx, "bite", "vampire_bite")
async def cmd_recruit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):await _single_target_cmd(update, ctx, "recruit", "cult_recruit")

async def handle_proceed_day(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    try:
        _, chat_id_str = data.split(":")
        chat_id = int(chat_id_str)
    except Exception:
        return
    game = GAMES.get(chat_id)
    if not game:
        await q.edit_message_text("No active game here.")
        return
    if q.from_user.id != game.host_id:
        await q.edit_message_text("Only the host can proceed to day.")
        return
    if game.phase != "night":
        await q.edit_message_text("It is not night.")
        return
    cancel_autoday(chat_id)
    res = game.resolve_night()
    winner = game.is_over()
    text = res + (f" {winner}." if winner else "")
    try:
        await q.edit_message_text("✅ Proceed ke siang sekarang.")
    except Exception:
        pass
    await ctx.bot.send_message(chat_id=chat_id, text=text)
    if game.phase != "over":
        await ctx.bot.send_message(chat_id=chat_id, text="Day phase. Use, /vote <name or number>. Host can /tally and /endday.")

FUN_EXITS = [
    "🛑 Game end weh, semua balik kampung dulu, next time jangan gaduh sangat.",
    "💥 Game cancelled, plot twist, semua kena culik UFO.",
    "🎭 Game stop, nanti kita sambung drama ni lagi.",
    "😌 Rehat jap, minum teh ais, next round kita all in."
]

def _quick_restart_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Start New Game", callback_data=f"start_newgame:{chat_id}")]])

def _build_summary_text(game: Game) -> str:
    lines = []
    lines.append("📜 Ringkasan game, players, role, status")
    for p in game.players.values():
        role = p.role.name if p.role else "Unassigned"
        status = "Alive" if p.alive else "Dead"
        lines.append(f"{p.name}, {role}, {status}")
    return "\n".join(lines)

async def cmd_exitgame(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active game here.")
        return
    game = GAMES[chat.id]
    if user.id != game.host_id:
        await update.effective_message.reply_text("Only the host can end the game.")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, end game", callback_data=f"exit_confirm:{chat.id}:yes")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"exit_confirm:{chat.id}:no")]
    ])
    await update.effective_message.reply_text("⚠ Betul nak end game ini, semua progress akan hilang.", reply_markup=kb)

async def handle_exit_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    try:
        _, chat_id_str, choice = data.split(":")
        chat_id = int(chat_id_str)
    except Exception:
        return
    game = GAMES.get(chat_id)
    if not game:
        try:
            await q.edit_message_text("No active game to end.")
        except Exception:
            pass
        return
    if q.from_user.id != game.host_id:
        await q.edit_message_text("Only the host can end the game.")
        return
    if choice != "yes":
        try:
            await q.edit_message_text("Cancel, game diteruskan.")
        except Exception:
            pass
        return
    try:
        cancel_autoday(chat_id)
    except Exception:
        pass
    summary = _build_summary_text(game)
    try:
        await q.edit_message_text("Ending game now.")
    except Exception:
        pass
    await ctx.bot.send_message(chat_id=chat_id, text=summary)
    fun = FUN_EXITS[0]
    try:
        import random as _r
        fun = _r.choice(FUN_EXITS)
    except Exception:
        pass
    await ctx.bot.send_message(chat_id=chat_id, text=fun, reply_markup=_quick_restart_keyboard(chat_id))
    try:
        del GAMES[chat_id]
    except KeyError:
        pass

async def handle_start_newgame(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    try:
        _, chat_id_str = data.split(":")
        chat_id = int(chat_id_str)
    except Exception:
        return
    host_id = q.from_user.id
    GAMES[chat_id] = Game(chat_id=chat_id, host_id=host_id)
    try:
        await q.edit_message_text("🎮 New game lobby created, host is you. Players, tekan /join, host boleh /startgame bila ready.")
    except Exception:
        await ctx.bot.send_message(chat_id=chat_id, text="🎮 New game lobby created, host is you. Players, tekan /join, host boleh /startgame bila ready.")

async def cmd_votebuttons(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active game here.")
        return
    game = GAMES[chat.id]
    if game.phase != "day":
        await update.effective_message.reply_text("It is not day right now.")
        return
    try:
        await update.effective_chat.send_message("🗳 Vote sekarang, pilih nama bawah", reply_markup=targets_keyboard(game, "vote"))
    except Exception as e:
        log.info("Vote keyboard failed, %s", e)


def teammates_for(user_id: int, game: Game) -> Dict[str, list]:
    packs = {}
    if user_id in game.wolves:
        packs["🐺 Wolves"] = [game.players[pid].name for pid in game.wolves if pid in game.players]
    if user_id in game.masons:
        packs["🧱 Masons"] = [game.players[pid].name for pid in game.masons if pid in game.players]
    if user_id in game.vampires:
        packs["🦇 Vampires"] = [game.players[pid].name for pid in game.vampires if pid in game.players]
    if user_id in game.cult:
        packs["🔮 Cult"] = [game.players[pid].name for pid in game.cult if pid in game.players]
    return packs

async def cmd_pack(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Find the game the user is in
    game = next((g for g in GAMES.values() if user.id in g.players), None)
    if game is None:
        await update.effective_message.reply_text("No active game for you.")
        return
    packs = teammates_for(user.id, game)
    if not packs:
        await update.effective_message.reply_text("You have no known teammates.")
        return
    lines = ["🤝 Your known teammates"]
    for label, names in packs.items():
        you = game.players[user.id].name if user.id in game.players else "You"
        # Do not duplicate the user's own name in the list
        filtered = [n for n in names if n != you]
        if not filtered:
            filtered = ["No others"]
        lines.append(f"{label}, " + ", ".join(filtered))
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_role(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # DM only, show your role and a one line tip
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.type != Chat.PRIVATE:
        return
    game = next((g for g in GAMES.values() if user.id in g.players), None)
    if not game:
        await update.effective_message.reply_text("You are not in any active game.")
        return
    p = game.players.get(user.id)
    if not p or not p.role:
        await update.effective_message.reply_text("No role assigned yet.")
        return
    role = p.role.name
    emoji = role_emoji(role)
    tips = {
        "Werewolf": "Bunuh seorang setiap malam. Guna butang Kill dalam DM.",
        "Wolf Cub": "Ikut geng serigala, undi mangsa setiap malam.",
        "Lone wolf": "Solo wolf, survive sampai akhir.",
        "Seer": "Intai alignment orang tiap malam, guna Peek.",
        "Aura Seer": "Baca aura, Wolf, Neutral, atau Village.",
        "Apprentice Seer": "Back up Seer, bila Seer mati kau ambil alih.",
        "Doctor": "Rawat seorang, sekali malam, guna Save.",
        "Bodyguard": "Protect seorang, jangan dua malam berturut pada orang sama.",
        "Witch": "Ada Heal dan Poison, sekali setiap satu sepanjang game.",
        "Vampire": "Bite orang untuk recruit, tengok syarat dalam DM.",
        "Cult Leader": "Recruit orang jadi cult masa malam.",
        "Mason": "Kau ada geng Mason, percaya sesama sendiri.",
        "Villager": "Siang banyak cakap, undi bijak, malam tidur."
    }
    tip = tips.get(role, "Main ikut instinct, baca chat, buat keputusan bijak.")
    await update.effective_message.reply_text(f"{emoji} Role kau, {role}. {tip}")



async def cmd_nextphase(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active game here.")
        return
    game = GAMES[chat.id]
    if user.id != game.host_id:
        await update.effective_message.reply_text("Only the host can change the phase.")
        return
    # Debounce
    if getattr(game,'started', False):
        await update.effective_message.reply_text('Game sudah bermula.')
        return
    game.started = True
    # send roles via DM now
    await send_roles_for_chat(chat.id, ctx)
    # Start Day 1 announcement and vote keyboard
    await update.effective_message.reply_text('🌞 Siang 1 bermula, masa borak dan undi. Guna butang undi di bawah.')
    await post_vote_keyboard(chat.id, ctx)

    if game.phase == "night":
        # Resolve night to day
        res = game.resolve_night()
        winner = game.is_over()
        await update.effective_message.reply_text(res + (f" {winner}." if winner else ""))
        if game.phase != "over":
            await update.effective_message.reply_text("🌞 Siang bermula, masa borak, tuduh, dan undi. Guna /vote <nama atau nombor>, atau /votebuttons untuk butang undi.")
    elif game.phase == "day":
        # End day to night
        res = game.end_day()
        await update.effective_message.reply_text(res)
        if game.phase != "over" and game.phase == "night":
            await update.effective_message.reply_text("🌙 Night bermula, role yang ada aksi, sila buat dalam DM.")
    else:
        await update.effective_message.reply_text(f"Phase sekarang, {game.phase}.")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    secret = os.getenv("WEBHOOK_SECRET", "dev-secret")
    port = int(os.getenv("PORT", "8000"))
    base_url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PUBLIC_BASE_URL")
    webhook_path = "/telegram/webhook"

    if not token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN environment variable.")
    if not base_url:
        raise RuntimeError("Set PUBLIC_BASE_URL to your Render URL, for example https://your-service.onrender.com")
    if base_url.startswith("http://"):
        base_url = "https://" + base_url.split("://", 1)[1]
    webhook_url = f"{base_url}{webhook_path}"

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("howtoplay", cmd_howtoplay))
    app.add_handler(CommandHandler("resendroles", cmd_resendroles))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("votes", cmd_votes))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("newgame", cmd_newgame))
    app.add_handler(CommandHandler("join", cmd_join))
    app.add_handler(CommandHandler("listalive", cmd_listalive))
    app.add_handler(CommandHandler("showroles", cmd_showroles))
    app.add_handler(CommandHandler("mayor", cmd_mayor))
    app.add_handler(CommandHandler("startgame", cmd_startgame))
    app.add_handler(CommandHandler("day", cmd_day))
    app.add_handler(CommandHandler("vote", cmd_vote))
    app.add_handler(CommandHandler("tally", cmd_tally))
    app.add_handler(CommandHandler("votebuttons", cmd_votebuttons))
    app.add_handler(CommandHandler("endday", cmd_endday))
    app.add_handler(CallbackQueryHandler(handle_nextphase_button, pattern=r"^nextphase:\d+$"))
    app.add_handler(CommandHandler("nextphase", cmd_nextphase))
    app.add_handler(CommandHandler("modboard", cmd_modboard))
    app.add_handler(CommandHandler("role", cmd_role))
    app.add_handler(CommandHandler("pack", cmd_pack))
    app.add_handler(CommandHandler("cheatroles", cmd_cheatroles))
    app.add_handler(CommandHandler("exitgame", cmd_exitgame))
    app.add_handler(MessageHandler(filters.Regex(r"^/start role_\d+$"), handle_start_deeplink))

    app.add_handler(CallbackQueryHandler(handle_action_button, pattern=r"^(kill|peek|aura|save|protect|heal|poison|bless|scry|bite|recruit):\d+$"))
    app.add_handler(CallbackQueryHandler(handle_action_button, pattern=r"^vote:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_proceed_day, pattern=r"^proceed_day:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_exit_confirm, pattern=r"^exit_confirm:\d+:(yes|no)$"))
    app.add_handler(CallbackQueryHandler(handle_start_newgame, pattern=r"^start_newgame:\d+$"))
    app.add_handler(CallbackQueryHandler(close_message_handler, pattern=r"^close_message$"))

    app.add_handler(CommandHandler("kill", cmd_kill))
    app.add_handler(CommandHandler("peek", cmd_peek))
    app.add_handler(CommandHandler("aura", cmd_aura))
    app.add_handler(CommandHandler("save", cmd_save))
    app.add_handler(CommandHandler("protect", cmd_protect))
    app.add_handler(CommandHandler("heal", cmd_heal))
    app.add_handler(CommandHandler("poison", cmd_poison))
    app.add_handler(CommandHandler("bless", cmd_bless))
    app.add_handler(CommandHandler("scry", cmd_scry))
    app.add_handler(CommandHandler("bite", cmd_bite))
    app.add_handler(CommandHandler("recruit", cmd_recruit))

    app.run_webhook(listen="0.0.0.0", port=port, url_path=webhook_path, webhook_url=webhook_url, secret_token=secret)

if __name__ == "__main__":
    main()
