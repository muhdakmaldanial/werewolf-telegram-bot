import os, json, io
import logging
from typing import Dict, Optional, List
from telegram import Update, Chat, User, Document
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from game.game import Game
from game.roles import *

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("werewolf-bot")

GAMES: Dict[int, Game] = {}
CHAT_PRESET: Dict[int, List[Role]] = {}
CONFIG_PATH = os.getenv("CONFIG_PATH", "data/roles.json")

# Presets
PRESETS = {
    "classic": ["Villager","Villager","Villager","Villager","Werewolf","Werewolf","Seer","Doctor","Hunter","Bodyguard","Witch","Mason"],
    "social": ["Villager","Villager","Villager","Werewolf","Seer","Doctor","Mayor","Prince","Cupid","Old Hag","Spellcaster","Pacifist"],
    "chaos":  ["Villager","Werewolf","Seer","Doctor","Witch","Bodyguard","Troublemaker","Vampire","Sorceress","Paranormal Investigator","Village Idiot","Tanner","Cursed","Lycan","Diseased"],
    "cult":   ["Villager","Villager","Werewolf","Seer","Doctor","Bodyguard","Witch","Cult Leader","Hoodlum","Mason","Prince"]
}

def roles_from_names(names: List[str]) -> List[Role]:
    out = []
    for n in names:
        r = ROLE_BY_NAME.get(n.strip().lower())
        if r is None:
            raise ValueError(f"Unknown role, {n}")
        out.append(r)
    return out

def roles_from_json_text(txt: str) -> List[Role]:
    data = json.loads(txt)
    if isinstance(data, list):
        return roles_from_names(data)
    if isinstance(data, dict):
        names = []
        for k, v in data.items():
            v = int(v)
            names += [k] * v
        return roles_from_names(names)
    raise ValueError("JSON must be a list of role names, or an object of name to count.")

def mention(u: User) -> str:
    if u.username:
        return f"@{u.username}"
    return u.full_name

def numbered_alive_list(game: Game) -> str:
    alive = sorted([p for p in game.players.values() if p.alive], key=lambda x: x.name.lower())
    if not alive:
        return "No living players."
    return "\n".join(f"{i+1}. {p.name}" for i, p in enumerate(alive))

def build_modboard_text(game: Game) -> str:
    lines = []
    for p in game.players.values():
        role_name = p.role.name if p.role else "Unassigned"
        status = "Alive" if p.alive else "Dead"
        cult_tag = ", Cult" if p.user_id in game.cult else ""
        lines.append(f"{p.name}, {role_name}{cult_tag}, {status}")
    return "Moderator board\n" + "\n".join(lines)

async def post_summary(update: Update, game: Game, header: str):
    alive = [p.name for p in game.players.values() if p.alive]
    silenced = ", ".join(game.name_of(x) for x in game.silenced_today) if game.silenced_today else "None"
    bound = ", ".join(game.name_of(x) for x in game.bound_next_night) if game.bound_next_night else "None"
    text = (
        f"{header}\n"
        f"Day, {game.day_count}\n"
        f"Alive count, {len(alive)}\n"
        f"Alive, {', '.join(sorted(alive, key=str.lower)) or 'None'}\n"
        f"Silenced today, {silenced}\n"
        f"Bound next night, {bound}"
    )
    await update.effective_chat.send_message(text)

# Core commands
async def cmd_howtoplay(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "Presets and roles\n"
        "Host, /preset name, presets, classic, social, chaos, cult\n"
        "Host, /showroles, see current roles list\n"
        "Host, /addrole RoleName, add one copy, Host, /removerole RoleName, remove one copy\n"
        "Host, upload JSON, send a file named roles.json, or paste with /setrolesjson <json>\n"
        "List form, [\"Villager\",\"Werewolf\"], Count form, {\"Villager\":6,\"Werewolf\":2}\n\n"
        "Game flow\n"
        "Group, /newgame, /join, /startgame, /listalive, /status, /vote, /tally, /endday, /mayor\n"
        "Night in DM, Wolves, /kill, Seer, /peek, Aura Seer, /aura, Doctor, /save, Bodyguard, /protect, Witch, /heal or /poison, "
        "Old Hag, /silence, Spellcaster, /bind a b, Cupid, /pair a b, Priest, /bless, Sorceress, /scry, Vamp, /bite, "
        "Paranormal Investigator, /check a [b], Troublemaker, /swap a b, Cult Leader, /recruit"
    )
    await update.effective_message.reply_text(text)

async def cmd_preset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.type == Chat.PRIVATE:
        await update.effective_message.reply_text("Use this in the group.")
        return
    if chat.id not in GAMES:
        await update.effective_message.reply_text("Create a lobby first with /newgame.")
        return
    game = GAMES[chat.id]
    if user.id != game.host_id:
        await update.effective_message.reply_text("Only the host can set presets.")
        return
    if not ctx.args:
        await update.effective_message.reply_text("Usage, /preset name, choices, " + ", ".join(PRESETS.keys()))
        return
    name = ctx.args[0].lower()
    if name not in PRESETS:
        await update.effective_message.reply_text("Unknown preset, choices, " + ", ".join(PRESETS.keys()))
        return
    CHAT_PRESET[chat.id] = roles_from_names(PRESETS[name])
    await update.effective_message.reply_text(f"Preset set to {name}. Use /showroles to view.")

async def cmd_showroles(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No lobby here.")
        return
    roles = CHAT_PRESET.get(chat.id) or DEFAULT_ROLESET
    names = [r.name for r in roles]
    await update.effective_message.reply_text("Current roles\n" + ", ".join(names))

async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("Pong, bot is online.")

async def cmd_modboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    # find the game this user is hosting
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

async def cmd_addrole(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No lobby here.")
        return
    game = GAMES[chat.id]
    if user.id != game.host_id:
        await update.effective_message.reply_text("Only the host can change roles.")
        return
    if not ctx.args:
        await update.effective_message.reply_text("Usage, /addrole RoleName")
        return
    name = " ".join(ctx.args)
    r = ROLE_BY_NAME.get(name.strip().lower())
    if not r:
        await update.effective_message.reply_text("Unknown role name.")
        return
    lst = CHAT_PRESET.get(chat.id) or list(DEFAULT_ROLESET)
    lst.append(r)
    CHAT_PRESET[chat.id] = lst
    await update.effective_message.reply_text(f"Added, {r.name}.")

async def cmd_removerole(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No lobby here.")
        return
    game = GAMES[chat.id]
    if user.id != game.host_id:
        await update.effective_message.reply_text("Only the host can change roles.")
        return
    if not ctx.args:
        await update.effective_message.reply_text("Usage, /removerole RoleName")
        return
    name = " ".join(ctx.args).strip().lower()
    lst = CHAT_PRESET.get(chat.id) or list(DEFAULT_ROLESET)
    for i, r in enumerate(lst):
        if r.name.lower() == name:
            lst.pop(i)
            CHAT_PRESET[chat.id] = lst
            await update.effective_message.reply_text(f"Removed, {r.name}.")
            return
    await update.effective_message.reply_text("That role is not in the list.")

async def cmd_setrolesjson(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No lobby here.")
        return
    game = GAMES[chat.id]
    if user.id != game.host_id:
        await update.effective_message.reply_text("Only the host can change roles.")
        return
    if not ctx.args:
        await update.effective_message.reply_text("Usage, /setrolesjson <json>")
        return
    txt = " ".join(ctx.args)
    try:
        roles = roles_from_json_text(txt)
    except Exception as e:
        await update.effective_message.reply_text(f"Invalid JSON, {e}")
        return
    CHAT_PRESET[chat.id] = roles
    await update.effective_message.reply_text("Roles updated from JSON.")

async def handle_roles_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or chat.type == Chat.PRIVATE:
        return
    if chat.id not in GAMES:
        return
    game = GAMES[chat.id]
    user = update.effective_user
    if user.id != game.host_id:
        return
    doc: Document = update.message.document
    if not doc or not doc.file_name.lower().endswith(".json"):
        return
    file = await ctx.bot.get_file(doc.file_id)
    bio = io.BytesIO()
    await file.download_to_memory(out=bio)
    txt = bio.getvalue().decode("utf-8")
    try:
        roles = roles_from_json_text(txt)
    except Exception as e:
        await update.effective_message.reply_text(f"Could not read roles.json, {e}")
        return
    CHAT_PRESET[chat.id] = roles
    # persist for this chat
    try:
        os.makedirs("data", exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump([r.name for r in roles], f)
    except Exception as e:
        log.warning("Persist failed, %s", e)
    await update.effective_message.reply_text("Roles updated from roles.json.")

# Game commands and actions
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    game = None
    if chat and chat.id in GAMES:
        game = GAMES[chat.id]
    else:
        for g in GAMES.values():
            if user.id in g.players:
                game = g
                break
    if game is None:
        await update.effective_message.reply_text("No active game here.")
        return
    phase = game.phase
    day = game.day_count
    last = game.name_of(game.last_killed) if game.last_killed else "None"
    alive = ", ".join(sorted([p.name for p in game.players.values() if p.alive], key=str.lower)) or "None"
    extra = ""
    if game.silenced_today:
        extra += " Silenced today, " + ", ".join(game.name_of(x) for x in game.silenced_today) + "."
    if game.bound_next_night:
        extra += " Bound next night, " + ", ".join(game.name_of(x) for x in game.bound_next_night) + "."
    await update.effective_message.reply_text(f"Status, phase, {phase}, day, {day}, last killed, {last}. Alive, {alive}.{extra}")

async def cmd_newgame(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.type == Chat.PRIVATE:
        await update.effective_message.reply_text("Use /newgame in a group chat.")
        return
    GAMES[chat.id] = Game(chat_id=chat.id, host_id=user.id)
    # try to load persisted roles
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                names = json.load(f)
                CHAT_PRESET[chat.id] = roles_from_names(names)
    except Exception as e:
        log.warning("Could not load roles.json, %s", e)
    await update.effective_message.reply_text("New Werewolf lobby created. Players use /join. Host uses /preset or upload roles.json, then /startgame when ready.")

async def cmd_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active lobby. Use /newgame first.")
        return
    game = GAMES[chat.id]
    res = game.add_player(user.id, mention(user))
    await update.effective_message.reply_text(res)

async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None or chat.id not in GAMES:
        await update.effective_message.reply_text("No active game here.")
        return
    game = GAMES[chat.id]
    names = game.list_players()
    if not names:
        await update.effective_message.reply_text("No players yet.")
        return
    await update.effective_message.reply_text("Players, " + ", ".join(names))

async def cmd_listalive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    game = None
    if chat and chat.id in GAMES:
        game = GAMES[chat.id]
    else:
        user = update.effective_user
        for g in GAMES.values():
            if user.id in g.players:
                game = g
                break
    if game is None:
        await update.effective_message.reply_text("No active game here.")
        return
    await update.effective_message.reply_text("Alive\n" + numbered_alive_list(game))

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
    roleset = CHAT_PRESET.get(chat.id) or DEFAULT_ROLESET
    res = game.assign_roles(roleset)
    await update.effective_message.reply_text(res)
    if game.phase == "night":
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
                if p.role is SPELLCASTER:
                    text += " You can bind two players, /bind <a> <b>."
                if p.role is CUPID:
                    text += " First night only, pair two lovers, /pair <a> <b>."
                if p.role is PRIEST:
                    text += " You can bless one player, /bless <target>."
                if p.role is SORCERESS:
                    text += " You can scry a Seer type, /scry <target>."
                if p.role is PARANORMAL_INV:
                    text += " You can check up to two, /check <a> [b]."
                if p.role is TROUBLEMAKER:
                    text += " First night only, you can swap two roles, /swap <a> <b>."
                if p.role is VAMPIRE:
                    text += " You can bite one target, /bite <target>."
                if p.role is CULT_LEADER:
                    text += " You can recruit one target, /recruit <target>."
                if p.role is MASON and mason_names:
                    text += " Your fellow Masons, " + ", ".join(n for n in mason_names if n != p.name)
                await ctx.bot.send_message(chat_id=pid, text=text)
            except Exception as e:
                log.warning("Failed to DM player %s: %s", p.name, e)
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
    await post_summary(update, game, "Night summary")
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
    await post_summary(update, game, "Day summary")
    if game.phase == "over":
        return
    if game.phase == "night":
        await update.effective_message.reply_text("Night phase. Night roles, act in DM.")

# Private commands, reusing Phase 3 methods
async def cmd_revealroles(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.type != Chat.PRIVATE:
        await update.effective_message.reply_text("Use this in a private chat with the bot.")
        return
    game = None
    for g in GAMES.values():
        if user.id in g.players:
            game = g
            break
    if game is None:
        await update.effective_message.reply_text("You are not in a game.")
        return
    if user.id != game.host_id:
        await update.effective_message.reply_text("Only the host can view the moderator board.")
        return
    lines = []
    for p in game.players.values():
        role_name = p.role.name if p.role else "Unassigned"
        status = "Alive" if p.alive else "Dead"
        cult_tag = ", Cult" if p.user_id in game.cult else ""
        lines.append(f"{p.name}, {role_name}{cult_tag}, {status}")
    await update.effective_message.reply_text("Moderator board\n" + "\n".join(lines))

# Wire the rest of role commands from earlier phases
from telegram.ext import CallbackContext
async def passthrough_private(update: Update, ctx: ContextTypes.DEFAULT_TYPE, method_name: str, need_two=False, alive_only=True):
    user = update.effective_user
    if update.effective_chat is None or update.effective_chat.type != Chat.PRIVATE:
        return
    game = next((g for g in GAMES.values() if user.id in g.players), None)
    if game is None:
        await update.effective_message.reply_text("You are not in a game.")
        return
    if need_two and len(ctx.args) < 2:
        await update.effective_message.reply_text("Two targets required.")
        return
    if need_two:
        a_id = game.resolve_target(ctx.args[0], alive_only=True)
        b_id = game.resolve_target(ctx.args[1], alive_only=True)
        if a_id is None or b_id is None:
            await update.effective_message.reply_text("No unique match for one of the players.")
            return
        res = getattr(game, method_name)(user.id, a_id, b_id)
    else:
        if not ctx.args:
            await update.effective_message.reply_text("Target required.")
            return
        target_id = game.resolve_target(" ".join(ctx.args), alive_only=alive_only)
        if target_id is None:
            await update.effective_message.reply_text("No unique match.")
            return
        res = getattr(game, method_name)(user.id, target_id)
    await update.effective_message.reply_text(res)

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_howtoplay(update, ctx)

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

    # group
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("howtoplay", cmd_howtoplay))
    app.add_handler(CommandHandler("preset", cmd_preset))
    app.add_handler(CommandHandler("showroles", cmd_showroles))
    app.add_handler(CommandHandler("addrole", cmd_addrole))
    app.add_handler(CommandHandler("removerole", cmd_removerole))
    app.add_handler(CommandHandler("setrolesjson", cmd_setrolesjson))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_roles_file))

    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("newgame", cmd_newgame))
    app.add_handler(CommandHandler("join", cmd_join))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("listalive", cmd_listalive))
    app.add_handler(CommandHandler("mayor", cmd_mayor))
    app.add_handler(CommandHandler("startgame", cmd_startgame))
    app.add_handler(CommandHandler("day", cmd_day))
    app.add_handler(CommandHandler("vote", cmd_vote))
    app.add_handler(CommandHandler("tally", cmd_tally))
    app.add_handler(CommandHandler("endday", cmd_endday))

    # private role commands, all pass through
    app.add_handler(CommandHandler("revealroles", cmd_revealroles))
    app.add_handler(CommandHandler("kill", lambda u,c: passthrough_private(u,c,"wolf_vote", need_two=False)))
    app.add_handler(CommandHandler("peek", lambda u,c: passthrough_private(u,c,"seer_peek", need_two=False)))
    app.add_handler(CommandHandler("aura", lambda u,c: passthrough_private(u,c,"aura_peek", need_two=False)))
    app.add_handler(CommandHandler("save", lambda u,c: passthrough_private(u,c,"doctor_save", need_two=False)))
    app.add_handler(CommandHandler("protect", lambda u,c: passthrough_private(u,c,"bodyguard_protect", need_two=False)))
    app.add_handler(CommandHandler("heal", lambda u,c: passthrough_private(u,c,"witch_heal", need_two=False, alive_only=False)))
    app.add_handler(CommandHandler("poison", lambda u,c: passthrough_private(u,c,"witch_poison", need_two=False)))
    app.add_handler(CommandHandler("silence", lambda u,c: passthrough_private(u,c,"old_hag_silence", need_two=False)))
    app.add_handler(CommandHandler("bind", lambda u,c: passthrough_private(u,c,"spellcaster_bind", need_two=True)))
    app.add_handler(CommandHandler("pair", lambda u,c: passthrough_private(u,c,"cupid_pair", need_two=True)))
    app.add_handler(CommandHandler("bless", lambda u,c: passthrough_private(u,c,"priest_bless", need_two=False)))
    app.add_handler(CommandHandler("scry", lambda u,c: passthrough_private(u,c,"sorceress_scry", need_two=False)))
    app.add_handler(CommandHandler("check", lambda u,c: passthrough_private(u,c,"pii_check", need_two=True)))
    app.add_handler(CommandHandler("bite", lambda u,c: passthrough_private(u,c,"vampire_bite", need_two=False)))
    app.add_handler(CommandHandler("swap", lambda u,c: passthrough_private(u,c,"troublemaker_swap", need_two=True)))
    app.add_handler(CommandHandler("recruit", lambda u,c: passthrough_private(u,c,"cult_recruit", need_two=False)))
    
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("modboard", cmd_modboard))


    app.run_webhook(listen="0.0.0.0", port=port, url_path=webhook_path, webhook_url=webhook_url, secret_token=secret)

if __name__ == "__main__":
    main()
