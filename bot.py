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
    lines = []
    for p in game.players.values():
        role_name = p.role.name if p.role else "Unassigned"
        status = "Alive" if p.alive else "Dead"
        cult_tag = ", Cult" if p.user_id in game.cult else ""
        lines.append(f"{p.name}, {role_name}{cult_tag}, {status}")
    return "Moderator board\n" + "\n".join(lines)

async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("Pong, bot is online.")

async def cmd_howtoplay(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    parts = [
        "How to play, Chaos Deck, all roles included\n1, Host, /newgame in group\n2, Everyone, tap /join\n3, Host, tap /startgame\n4, Bot DMs your role, keep it secret",
        "Day phase\nDiscuss in group, use /status, use /listalive to see living players",
        "Night phase\nRoles get DM buttons, Kill, Peek, Aura, Save, Protect, Heal, Poison, Bless, Scry, Bite, Recruit",
        "Group commands\n/join, join lobby\n/status, show players\n/listalive, list living\n/startgame, host only\n/tally, show votes\n/endday, advance to night\n/modboard, host only",
        "DM commands, shows target buttons if no name is typed\n/kill, wolves\n/peek, seer\n/aura, aura seer\n/save, doctor\n/protect, bodyguard\n/heal, witch\n/poison, witch\n/bless, priest\n/scry, sorceress\n/bite, vampire\n/recruit, cult leader",
        "Tips\nCheck your DM at night\nUse buttons for targets\nNumbers work, try /listalive then pick a number",
    ]
    sent0 = await update.effective_message.reply_text(parts[0])
    try:
        await sent0.pin()
    except Exception as e:
        log.info("Pin failed, %s", e)
    await asyncio.sleep(0.5)
    for txt in parts[1:]:
        await update.effective_chat.send_message(txt)
        await asyncio.sleep(0.4)

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
    alive = ", ".join(sorted([p.name for p in game.players.values() if p.alive], key=str.lower)) or "None"
    await update.effective_message.reply_text(
        f"Status, phase, {phase}, day, {day}, last killed, {last}. Alive, {alive}.",
        reply_markup=group_keyboard(is_host=(game.host_id == user.id))
    )

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
        await update.effective_message.reply_text(
            f"Starting game with Chaos Deck. Players, {len(game.players)}. Assigning roles from the full deck."
        )
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
        await update.effective_message.reply_text("Night has begun. Use /howtoplay for the guide.")

async def cmd_day(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active game here.")
        return
    game = GAMES[chat.id]
    if game.phase != "night":
        await update.effective_message.reply_text("It is not night.")
        return
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
        await update.effective_message.reply_text("No votes yet.")
        return
    lines = [f"{game.name_of(pid)}: {count}" for pid, count in t.items()]
    await update.effective_message.reply_text("Votes\n" + "\n".join(lines))

async def cmd_endday(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active game here.")
        return
    game = GAMES[chat.id]
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
    method = mapping.get(action)
    if not method:
        await q.edit_message_text("Action not supported.")
        return
    res = getattr(game, method)(user.id, target_id)
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

    app.add_handler(CallbackQueryHandler(handle_action_button, pattern=r"^(kill|peek|aura|save|protect|heal|poison|bless|scry|bite|recruit):\d+$"))
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
