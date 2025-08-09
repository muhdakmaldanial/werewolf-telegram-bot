import os, asyncio, logging
from typing import Dict
from telegram import Update, Chat, User, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from game.game import Game
from game.roles import *

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("werewolf-bot")

GAMES: Dict[int, Game] = {}
CHAOS_DECK = ALL_ROLES

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
    if user.id != game.host_id:
        await update.effective_message.reply_text("Only the host can view pending actions.")
        return
    items = game.pending_summary()
    txt = "⏳ Pending\n" + "\n".join(items)
    if items == ["All required night actions are in"] and game.phase == "night":
        await update.effective_message.reply_text(txt + "\n⚡ Semua action masuk, auto proceed ke siang dalam 45 saat ⏳", reply_markup=proceed_button(chat.id))
        await schedule_autoday(chat.id, ctx, delay_secs=45)
    else:
        await update.effective_message.reply_text(txt)

async def cmd_newgame(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.type == Chat.PRIVATE:
        await update.effective_message.reply_text("Use /newgame in a group chat.")
        return
    GAMES[chat.id] = Game(chat_id=chat.id, host_id=user.id)
    await update.effective_message.reply_text(
        "New Werewolf lobby created. Preset, Chaos Deck, all roles included. Players use /join. Host uses /startgame when ready.",
        reply_markup=group_keyboard(is_host=True)
    )

async def cmd_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active lobby. Use /newgame first.")
        return
    game = GAMES[chat.id]
    res = game.add_player(user.id, mention(user))
    await update.effective_message.reply_text(res, reply_markup=group_keyboard(is_host=(game.host_id == user.id)))

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
    if len(game.players) < 5:
    await update.effective_message.reply_text("⚠️ Kena ada minimum 6 orang baru boleh start game. Jom ajak kawan lagi!")
    return
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active lobby. Use /newgame first.")
        return
    game = GAMES[chat.id]
    if user.id != game.host_id:
        await update.effective_message.reply_text("Only the host can start the game.")
        return
    roleset = CHAOS_DECK
    res = game.assign_roles(roleset)
    await update.effective_message.reply_text(res)
    if game.phase == "night":
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
                await ctx.bot.send_message(chat_id=pid, text=text)
                if p.role in (WEREWOLF, WOLF_CUB, LONE_WOLF, SEER, AURA_SEER, DOCTOR, BODYGUARD, WITCH, PRIEST, SORCERESS, VAMPIRE, CULT_LEADER):
                    action_map = {SEER:"peek", AURA_SEER:"aura", DOCTOR:"save", BODYGUARD:"protect", WITCH:"heal", PRIEST:"bless", SORCERESS:"scry", VAMPIRE:"bite", CULT_LEADER:"recruit", WEREWOLF:"kill", WOLF_CUB:"kill", LONE_WOLF:"kill"}
                    await ctx.bot.send_message(chat_id=pid, text="Quick targets", reply_markup=targets_keyboard(game, action_map[p.role]))
            except Exception as e:
                log.warning("Failed to DM player %s, %s", p.name, e)
        await update.effective_message.reply_text("🌙 Malam bermula, check DM untuk aksi. Aku akan pin cara main untuk semua.")
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
    if game.phase == "night":
        await update.effective_message.reply_text("Night phase. Night roles, act in DM.")

async def handle_action_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    try:
        action, target_str = data.split(":")
        target_id = int(target_str)
    except Exception:
        await q.edit_message_text("Bad button data.")
        return
    user = q.from_user
    game = next((g for g in GAMES.values() if user.id in g.players), None)
    if game is None:
        await q.edit_message_text("You are not in a game.")
        return
    mapping = {"kill":"wolf_vote","peek":"seer_peek","aura":"aura_peek","save":"doctor_save","protect":"bodyguard_protect","heal":"witch_heal","poison":"witch_poison","bless":"priest_bless","scry":"sorceress_scry","bite":"vampire_bite","recruit":"cult_recruit"}
    if not hasattr(game, mapping.get(action, "")):
        await q.edit_message_text("Action not supported.")
        return
    res = getattr(game, mapping[action])(user.id, target_id)
    try:
        await q.edit_message_text(f"{res}")
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
    app.add_handler(CommandHandler("endday", cmd_endday))
    app.add_handler(CommandHandler("modboard", cmd_modboard))
    app.add_handler(CommandHandler("cheatroles", cmd_cheatroles))
    app.add_handler(CommandHandler("exitgame", cmd_exitgame))

    app.add_handler(CallbackQueryHandler(handle_action_button, pattern=r"^(kill|peek|aura|save|protect|heal|poison|bless|scry|bite|recruit):\d+$"))
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
