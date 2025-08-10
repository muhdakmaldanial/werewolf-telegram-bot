
import os, asyncio, logging, random
from typing import Dict, Tuple
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, filters
from game.game import Game
from game.roles import ALL_ROLES

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("werewolf-bot")

MIN_PLAYERS = int(os.getenv("MIN_PLAYERS", "5"))
BOT_TOKEN = ( os.getenv("BOT_TOKEN", "")          # standard
    or os.getenv("TELEGRAM_BOT_TOKEN")            # some repos use this
    or os.getenv("TELEGRAM_TOKEN")                # some repos use this
    or os.getenv("TOKEN")                         # fallback generic
            )
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
PORT = int(os.getenv("PORT", "10000"))

# thread-safe map, key is (chat_id, thread_id_or_0)
GAMES: Dict[Tuple[int,int], Game] = {}
HOWTO_PINNED = set()

def key_of(update: Update) -> Tuple[int,int]:
    chat_id = update.effective_chat.id
    thr = getattr(update.effective_message, "message_thread_id", None) or 0
    return (chat_id, thr)

async def pin_howto_once(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in HOWTO_PINNED:
        return
    msg = await update.effective_message.reply_text(
        "🐺 Werewolf, cara main, host, /newgame, semua /join, host /startgame. Day, vote, Night, actions DM. Enjoy."
    )
    try:
        await ctx.bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id)
    except Exception:
        pass
    HOWTO_PINNED.add(chat_id)

async def cmd_newgame(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    k = key_of(update)
    GAMES.pop(k, None)
    g = Game(chat_id=k[0], thread_id=k[1])
    g.host_id = update.effective_user.id
    g.phase = "lobby"
    GAMES[k] = g
    await pin_howto_once(update, ctx)
    await update.effective_message.reply_text(
        f"New Werewolf lobby created. Host @{update.effective_user.username or update.effective_user.first_name}. Players /join. Host /startgame."
    )

async def cmd_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    k = key_of(update)
    g = GAMES.get(k)
    if not g or g.phase != "lobby":
        await update.effective_message.reply_text("No active lobby. Use /newgame first.")
        return
    uid = update.effective_user.id
    if uid in g.players:
        await update.effective_message.reply_text("You are already in the lobby.")
        return
    g.add_player(uid, update.effective_user.full_name)
    await update.effective_message.reply_text(f"{update.effective_user.full_name} joined the lobby.")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    k = key_of(update); g = GAMES.get(k)
    if not g:
        await update.effective_message.reply_text("No game here.")
        return
    await update.effective_message.reply_text(f"Phase, {g.phase}, day, {g.day}, players, {len(g.players)}")

async def dm_roles_or_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE, g: Game):
    me = await ctx.bot.get_me()
    missing=[]
    for uid, ps in g.players.items():
        try:
            await ctx.bot.send_message(chat_id=uid, text=f"🎭 Role kau, {ps.role.name}.")
        except Exception:
            missing.append(uid)
    if missing:
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔒 Open DM to receive your role", url=f"https://t.me/{me.username}?start=role_{g.chat_id}_{g.thread_id}")]])
        await update.effective_message.reply_text("Ada pemain belum buka DM bot. Tap butang ini, tekan Start. Host boleh /resendroles.", reply_markup=btn)

async def cmd_startgame(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    k = key_of(update); g = GAMES.get(k)
    if not g or g.phase != "lobby":
        await update.effective_message.reply_text("No active lobby. Use /newgame first.")
        return
    # host or admin
    if update.effective_user.id != g.host_id:
        m = await ctx.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        if m.status not in ("administrator","creator"):
            await update.effective_message.reply_text("Only the host can start the game.")
            return
    if len(g.players) < MIN_PLAYERS:
        await update.effective_message.reply_text(f"Need at least {MIN_PLAYERS} players to start.")
        return
    g.assign_roles(ALL_ROLES)
    await dm_roles_or_panel(update, ctx, g)
    await update.effective_message.reply_text("🌞 Siang 1 bermula, masa borak dan undi.")
    await cmd_votebuttons(update, ctx)

async def cmd_resendroles(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    k = key_of(update); g = GAMES.get(k)
    if not g:
        await update.effective_message.reply_text("No active game here.")
        return
    await dm_roles_or_panel(update, ctx, g)

async def cmd_start_private(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text or ""
    parts = text.split(maxsplit=1)
    payload = parts[1] if len(parts)>1 else ""
    if payload.startswith("role_"):
        try:
            _, chat_id_str, thread_id_str = payload.split("_", 2)
            k=(int(chat_id_str), int(thread_id_str))
            g=GAMES.get(k)
            if not g:
                await update.effective_message.reply_text("No active game for that chat.")
                return
            uid = update.effective_user.id
            if uid not in g.players:
                await update.effective_message.reply_text("Join lobby dalam group dulu.")
                return
            await update.effective_message.reply_text(f"🎭 Role kau, {g.players[uid].role.name}.")
        except Exception:
            await update.effective_message.reply_text("Hi, tekan Start. Role dihantar bila host mula game.")
    else:
        await update.effective_message.reply_text("Hi, tekan Start. Role dihantar bila host mula game.")

# --- Voting ---
async def post_vote_keyboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE, g: Game):
    rows=[]
    alive = g.alive_list()
    num_map = g.list_alive_numbers()
    for uid in alive:
        label = f"{num_map[uid]}. {g.players[uid].name}"
        rows.append([InlineKeyboardButton(label, callback_data=f"vote:{uid}")])
    rows.append([InlineKeyboardButton("⏭ Skip", callback_data="vote:skip")])
    kb=InlineKeyboardMarkup(rows)
    msg = await ctx.bot.send_message(chat_id=g.chat_id, text="🗳 Vote sekarang", reply_markup=kb, message_thread_id=g.thread_id or None)
    g.vote_msg_id = msg.message_id

async def cmd_votebuttons(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    k=key_of(update); g=GAMES.get(k)
    if not g or g.phase!="day":
        await update.effective_message.reply_text("No active day here.")
        return
    await post_vote_keyboard(update, ctx, g)

async def handle_vote(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    k=key_of(update); g=GAMES.get(k)
    if not g or g.phase!="day": return
    voter=q.from_user.id
    if voter not in g.players or not g.players[voter].alive: return
    data=q.data.split(":")[1]
    target = data if data=="skip" else int(data)
    msg = g.vote(voter, target)
    await ctx.bot.send_message(chat_id=g.chat_id, text=f"✅ {g.players[voter].name} voted.", message_thread_id=g.thread_id or None)

async def cmd_tally(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    k=key_of(update); g=GAMES.get(k)
    if not g or g.phase!="day":
        await update.effective_message.reply_text("No active day here.")
        return
    target, tie = g.tally()
    if tie or not target:
        await update.effective_message.reply_text("🧮 Kiraan undi, tiada majoriti.")
    else:
        await update.effective_message.reply_text(f"🧮 Kiraan undi, paling banyak, {g.players[target].name}.")

async def cmd_nextphase(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    k=key_of(update); g=GAMES.get(k)
    if not g:
        await update.effective_message.reply_text("No active game here.")
        return
    # host or admin only
    if update.effective_user.id != g.host_id:
        m = await ctx.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        if m.status not in ("administrator","creator"):
            await update.effective_message.reply_text("Only the host can change phase.")
            return
    if g.phase=="day":
        text = g.resolve_day()
        await update.effective_message.reply_text(text)
    elif g.phase=="night":
        text = g.resolve_night()
        await update.effective_message.reply_text(text)
    else:
        await update.effective_message.reply_text("Not in a running game.")

async def cmd_claimhost(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    k=key_of(update); g=GAMES.get(k)
    if not g or g.phase!="lobby":
        await update.effective_message.reply_text("No game lobby found.")
        return
    m = await ctx.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if update.effective_user.id not in g.players and m.status not in ("administrator","creator"):
        await update.effective_message.reply_text("Join the lobby first or be an admin.")
        return
    g.host_id = update.effective_user.id
    await update.effective_message.reply_text(f"You are now the host, {update.effective_user.first_name}.")

# Night action buttons in DM (basic mapping)
async def handle_action_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    data=q.data; klist=[]
    try:
        action, target = data.split(":")
        target = int(target)
    except:
        return
    # find the game where this user exists
    game=None
    for key,g in GAMES.items():
        if q.from_user.id in g.players: game=g; break
    if not game or game.phase!="night":
        await q.edit_message_text("Action only at night, in DM.")
        return
    mapping={
        "kill":"wolf_kill","peek":"seer_peek","aura":"aura_peek","save":"doctor_save","protect":"bodyguard_protect",
        "heal":"witch_heal","poison":"witch_poison","bless":"priest_bless","scry":"sorceress_scry","bite":"vampire_bite","recruit":"cult_recruit"
    }
    meth=mapping.get(action)
    if not meth or not hasattr(game, meth):
        await q.edit_message_text("Action not supported here.")
        return
    res=getattr(game, meth)(q.from_user.id, target)
    await q.edit_message_text(res)

# Minimal target keyboard for DM
def targets_keyboard(g: Game, action: str):
    alive=g.alive_list()
    rows=[[InlineKeyboardButton(g.players[uid].name, callback_data=f"{action}:{uid}")] for uid in alive]
    return InlineKeyboardMarkup(rows)

# Entry points to start night DMs, you may call these when entering night
async def dm_night_prompts(update: Update, ctx: ContextTypes.DEFAULT_TYPE, g: Game):
    # Wolves
    for uid in list(g.wolves):
        try:
            await ctx.bot.send_message(chat_id=uid, text="🐺 Pilih mangsa", reply_markup=targets_keyboard(g,"kill"))
        except: pass
    # Seer
    for uid,ps in g.players.items():
        if ps.role.name=="Seer" and ps.alive:
            try:
                await ctx.bot.send_message(chat_id=uid, text="🔮 Pilih target", reply_markup=targets_keyboard(g,"peek"))
            except: pass
    # Doctor, Bodyguard, Witch, Vampire, Cult, Priest, Sorceress, Aura
    for uid,ps in g.players.items():
        if ps.role.name=="Doctor" and ps.alive:
            try: await ctx.bot.send_message(chat_id=uid, text="💉 Save siapa", reply_markup=targets_keyboard(g,"save"))
            except: pass
        if ps.role.name=="Bodyguard" and ps.alive:
            try: await ctx.bot.send_message(chat_id=uid, text="🛡 Protect siapa", reply_markup=targets_keyboard(g,"protect"))
            except: pass
        if ps.role.name=="Witch" and ps.alive:
            try: await ctx.bot.send_message(chat_id=uid, text="🧪 Heal siapa", reply_markup=targets_keyboard(g,"heal"))
            except: pass
            try: await ctx.bot.send_message(chat_id=uid, text="☠️ Poison siapa", reply_markup=targets_keyboard(g,"poison"))
            except: pass
        if ps.role.name=="Vampire" and ps.alive:
            try: await ctx.bot.send_message(chat_id=uid, text="🧛 Bite siapa", reply_markup=targets_keyboard(g,"bite"))
            except: pass
        if ps.role.name=="Cult Leader" and ps.alive:
            try: await ctx.bot.send_message(chat_id=uid, text="✝ Recruit siapa", reply_markup=targets_keyboard(g,"recruit"))
            except: pass
        if ps.role.name=="Priest" and ps.alive:
            try: await ctx.bot.send_message(chat_id=uid, text="✨ Bless siapa", reply_markup=targets_keyboard(g,"bless"))
            except: pass
        if ps.role.name=="Sorceress" and ps.alive:
            try: await ctx.bot.send_message(chat_id=uid, text="🧿 Scry siapa", reply_markup=targets_keyboard(g,"scry"))
            except: pass
        if ps.role.name=="Aura Seer" and ps.alive:
            try: await ctx.bot.send_message(chat_id=uid, text="🌈 Aura siapa", reply_markup=targets_keyboard(g,"aura"))
            except: pass

async def cmd_nextnight(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # convenience, end day and start night prompts
    k=key_of(update); g=GAMES.get(k)
    if not g: 
        await update.effective_message.reply_text("No game here.")
        return
    if g.phase!="day":
        await update.effective_message.reply_text("Not in day.")
        return
    await update.effective_message.reply_text(g.resolve_day())
    await dm_night_prompts(update, ctx, g)

async def cmd_nextday(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    k=key_of(update); g=GAMES.get(k)
    if not g: 
        await update.effective_message.reply_text("No game here.")
        return
    if g.phase!="night":
        await update.effective_message.reply_text("Not in night.")
        return
    await update.effective_message.reply_text(g.resolve_night())
    await cmd_votebuttons(update, ctx)

def build_app():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    # commands
    app.add_handler(CommandHandler("newgame", cmd_newgame))
    app.add_handler(CommandHandler("join", cmd_join))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("startgame", cmd_startgame))
    app.add_handler(CommandHandler("resendroles", cmd_resendroles))
    app.add_handler(CommandHandler("nextphase", cmd_nextphase))
    app.add_handler(CommandHandler("night2day", cmd_nextday))
    app.add_handler(CommandHandler("votebuttons", cmd_votebuttons))
    app.add_handler(CommandHandler("start", cmd_start_private, filters.ChatType.PRIVATE))
    # callbacks
    app.add_handler(CallbackQueryHandler(handle_vote, pattern=r"^vote:(.+)$"))
    app.add_handler(CallbackQueryHandler(handle_action_button, pattern=r"^(kill|peek|aura|save|protect|heal|poison|bless|scry|bite|recruit):\d+$"))
    return app

def main():
    # Optional local file fallback, do not commit your token
    if not BOT_TOKEN:
        try:
            # create local_config.py with a line, TELEGRAM_TOKEN = "123:ABC..."
            from local_config import TELEGRAM_TOKEN as _LOCAL_TOKEN
            BOT_TOKEN = _LOCAL_TOKEN
        except Exception:
            pass

    # Final check with a clear message
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN not found, set env BOT_TOKEN, or TELEGRAM_BOT_TOKEN, "
            "or create local_config.py with TELEGRAM_TOKEN = '123:ABC...'"
        )
    app = build_app()
    # set UI commands
    try:
        app.bot.set_my_commands([
            BotCommand("newgame","Buka lobby"),
            BotCommand("join","Masuk lobby"),
            BotCommand("startgame","Host mula game"),
            BotCommand("status","Status game"),
            BotCommand("votebuttons","Butang undi siang"),
            BotCommand("nextphase","Tamat siang ke malam"),
            BotCommand("night2day","Tamat malam ke siang"),
        ])
    except Exception:
        pass
    if WEBHOOK_URL:
        app.run_webhook(listen="0.0.0.0", port=PORT, url_path="webhook", webhook_url=f"{WEBHOOK_URL}/webhook")
    else:
        app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
