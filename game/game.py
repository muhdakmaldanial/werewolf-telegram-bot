from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import random
from .roles import *

@dataclass
class Player:
    user_id: int
    name: str
    role: Optional[Role] = None
    alive: bool = True

@dataclass
class Game:
    chat_id: int
    host_id: int
    players: Dict[int, Player] = field(default_factory=dict)
    phase: str = "lobby"
    day_count: int = 0

    wolves: Set[int] = field(default_factory=set)
    vampires: Set[int] = field(default_factory=set)
    cult: Set[int] = field(default_factory=set)

    lovers: Optional[Tuple[int, int]] = None
    masons: Set[int] = field(default_factory=set)

    silenced_today: Set[int] = field(default_factory=set)
    bound_next_night: Set[int] = field(default_factory=set)

    blessed: Optional[int] = None
    tough_guy_pending_death: Optional[int] = None
    prince_revealed: Set[int] = field(default_factory=set)
    mayor_revealed: Optional[int] = None
    hoodlum_marks: Optional[Tuple[int, int]] = None

    bodyguard_last_target: Optional[int] = None
    witch_heal_available: bool = True
    witch_poison_available: bool = True
    wolf_cub_lynched_yesterday: bool = False
    wolves_skip_kill_tonight: bool = False

    wolf_votes: Dict[int, int] = field(default_factory=dict)
    seer_target: Optional[int] = None
    aura_target: Optional[int] = None
    sorceress_target: Optional[int] = None
    priest_target: Optional[int] = None
    pii_first: Optional[int] = None
    pii_second: Optional[int] = None
    doctor_target: Optional[int] = None
    bodyguard_target: Optional[int] = None
    witch_heal_target: Optional[int] = None
    witch_poison_target: Optional[int] = None
    old_hag_target: Optional[int] = None
    spell_bind: Optional[Tuple[int, int]] = None
    vampire_target: Optional[int] = None
    trouble_swap: Optional[Tuple[int, int]] = None
    cult_target: Optional[int] = None

    day_votes: Dict[int, int] = field(default_factory=dict)
    last_killed: Optional[int] = None

    def add_player(self, user_id: int, name: str) -> str:
        if self.phase != "lobby":
            return "Game already started, wait for the next round."
        if user_id in self.players:
            return "You are already in the lobby."
        self.players[user_id] = Player(user_id=user_id, name=name)
        return f"{name} joined the lobby."

    def list_players(self) -> List[str]:
        return [p.name for p in self.players.values()]

    def assign_roles(self, roleset: Optional[List[Role]] = None) -> str:
        if self.phase != "lobby":
            return "Game already started."
        if len(self.players) < 5:
            return "Need at least 5 players."
        roles = list(roleset or DEFAULT_ROLESET)
        if len(roles) < len(self.players):
            roles += [VILLAGER] * (len(self.players) - len(roles))
        elif len(roles) > len(self.players):
            roles = roles[:len(self.players)]
        random.shuffle(roles)

        self.wolves.clear()
        self.vampires.clear()
        self.cult.clear()
        self.masons.clear()
        self.prince_revealed.clear()
        self.mayor_revealed = None
        self.bodyguard_last_target = None
        self.witch_heal_available = True
        self.witch_poison_available = True
        self.lovers = None
        self.hoodlum_marks = None
        self.trouble_swap = None
        self.wolves_skip_kill_tonight = False
        self.cult_target = None

        for p, r in zip(self.players.values(), roles):
            p.role = r
            if r in (WEREWOLF, WOLF_CUB, LONE_WOLF, MINION):
                self.wolves.add(p.user_id)
            if r is VAMPIRE:
                self.vampires.add(p.user_id)
            if r is MASON:
                self.masons.add(p.user_id)
            if r is CULT_LEADER:
                self.cult.add(p.user_id)

        self.phase = "night"
        self.day_count = 0
        self.wolf_votes.clear()
        self.day_votes.clear()
        self.silenced_today.clear()
        self.bound_next_night.clear()
        return "Roles assigned, night begins."

    def living(self) -> List[Player]:
        return [p for p in self.players.values() if p.alive]

    def name_of(self, user_id: int) -> str:
        return self.players[user_id].name if user_id in self.players else str(user_id)

    def alignment_for_seer(self, target: Player) -> str:
        if target.user_id in self.cult:
            return "Neutral team"
        if target.role in (WEREWOLF, WOLF_CUB, LONE_WOLF, MINION):
            return "Wolf team"
        if target.role is LYCAN:
            return "Wolf team"
        return "not Wolf team"

    def aura_for_aura_seer(self, target: Player) -> str:
        if target.role in (WEREWOLF, WOLF_CUB, LONE_WOLF, MINION):
            return "Wolf aura"
        if target.role in (VAMPIRE, HOODLUM, TANNER) or target.user_id in self.cult:
            return "Neutral aura"
        return "Village aura"

    def is_over(self) -> Optional[str]:
        alive = [p for p in self.players.values() if p.alive]
        wolves_alive = [p for p in alive if p.role in (WEREWOLF, WOLF_CUB, LONE_WOLF, MINION)]
        vampires_alive = [p for p in alive if p.user_id in self.vampires]
        cult_alive = [p for p in alive if p.user_id in self.cult]
        villagers_alive = [p for p in alive if p.user_id not in self.cult and p.role not in (WEREWOLF, WOLF_CUB, LONE_WOLF, MINION, VAMPIRE, HOODLUM, TANNER)]

        if self.lovers:
            a, b = self.lovers
            if self.players.get(a).alive and self.players.get(b).alive and len(alive) == 2:
                return "Lovers win"

        if len(alive) == 1 and alive[0].role is LONE_WOLF:
            return "Lone Wolf wins"

        if vampires_alive and len(vampires_alive) == len(alive):
            return "Vampires win"

        if cult_alive and len(cult_alive) > len(alive) - len(cult_alive):
            return "Cult wins"

        if not wolves_alive and not vampires_alive and not cult_alive:
            return "Village wins"
        if len(wolves_alive) >= len(villagers_alive) and not vampires_alive and not cult_alive:
            return "Wolves win"
        return None

    def living_index_map(self) -> Dict[str, int]:
        alive = sorted([p for p in self.players.values() if p.alive], key=lambda x: x.name.lower())
        return {str(i+1): alive[i].user_id for i in range(len(alive))}

    def resolve_target(self, token: str, alive_only=True) -> Optional[int]:
        token = (token or "").strip().lower()
        if not token:
            return None
        m = self.living_index_map()
        if token in m:
            return m[token]
        pool = [p for p in self.players.values() if (p.alive or not alive_only)]
        exact = [p for p in pool if p.name.lower() == token]
        if len(exact) == 1:
            return exact[0].user_id
        if len(token) >= 2:
            pref = [p for p in pool if p.name.lower().startswith(token)]
            if len(pref) == 1:
                return pref[0].user_id
        sub = [p for p in pool if token in p.name.lower()]
        if len(sub) == 1:
            return sub[0].user_id
        return None

    # Night actions, same as Phase 3, omitted here for brevity
    # We will import Phase 3 logic in the bot and call the same methods
