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
        roles = list(roleset or [VILLAGER]*len(self.players))
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

        self.phase = "day"
        self.day_count = 1
        self.wolf_votes.clear()
        self.day_votes.clear()
        self.silenced_today.clear()
        self.bound_next_night.clear()
        return "🌞 Siang 1 bermula, masa borak dan vote."

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

    def pending_summary(self) -> List[str]:
        out: List[str] = []
        if self.phase != "night":
            return ["Night actions are not pending, it is not night."]
        if not self.wolf_votes and any(self.players[pid].alive and self.players[pid].role in (WEREWOLF, WOLF_CUB, LONE_WOLF) for pid in self.wolves):
            out.append("Wolves, pending")
        if self.seer_target is None and any(p.alive and p.role is SEER for p in self.players.values()):
            out.append("Seer, pending")
        if self.aura_target is None and any(p.alive and p.role is AURA_SEER for p in self.players.values()):
            out.append("Aura Seer, pending")
        if self.doctor_target is None and any(p.alive and p.role is DOCTOR for p in self.players.values()):
            out.append("Doctor, pending")
        if self.bodyguard_target is None and any(p.alive and p.role is BODYGUARD for p in self.players.values()):
            out.append("Bodyguard, pending")
        if self.witch_heal_available and self.witch_heal_target is None and any(p.alive and p.role is WITCH for p in self.players.values()):
            out.append("Witch heal, available, optional")
        if self.witch_poison_available and self.witch_poison_target is None and any(p.alive and p.role is WITCH for p in self.players.values()):
            out.append("Witch poison, available, optional")
        if self.priest_target is None and any(p.alive and p.role is PRIEST for p in self.players.values()):
            out.append("Priest, pending")
        if self.sorceress_target is None and any(p.alive and p.role is SORCERESS for p in self.players.values()):
            out.append("Sorceress, pending")
        if self.vampire_target is None and any(pid in self.vampires and self.players[pid].alive for pid in self.vampires):
            out.append("Vampire, pending")
        if self.cult_target is None and any(pid in self.cult and self.players[pid].alive for pid in self.cult):
            out.append("Cult Leader, pending")
        return out or ["All required night actions are in"]

    def vote(self, voter_id: int, target_id: int) -> str:
        if self.phase != "day":
            return "It is not day."
        if voter_id not in self.players or not self.players[voter_id].alive:
            return "Only living players can vote."
        if voter_id in self.silenced_today:
            return "You are silenced and cannot vote today."
        # target_id == -1 means skip lynch
        if target_id != -1:
            if target_id not in self.players or not self.players[target_id].alive:
                return "Invalid target."
        self.day_votes[voter_id] = target_id
        return "Vote recorded on Skip" if target_id == -1 else f"Vote recorded on {self.name_of(target_id)}."

    def votes_progress(self) -> Tuple[int, int]:
        eligible = [p.user_id for p in self.players.values() if p.alive and p.user_id not in self.silenced_today]
        return len(self.day_votes), len(eligible)

    def tally(self) -> Dict[int, int]:
        t: Dict[int, int] = {}
        for voter, target in self.day_votes.items():
            weight = 1
            if self.mayor_revealed == voter:
                weight = 2
            if self.players[voter].role is VILLAGE_IDIOT:
                weight = 0
            t[target] = t.get(target, 0) + weight
        return t

    def end_day(self) -> str:
        if self.phase != "day":
            return "It is not day."
        tally = self.tally()
        if not tally:
            self.phase = "day"
            self.day_votes.clear()
            return "⏳ No votes cast, moving to Night."
        max_votes = max(tally.values())
        top = [t for t, v in tally.items() if v == max_votes]
        if -1 in top or len(top) > 1 or max_votes == 0:
            self.phase = "day"
            self.day_votes.clear()
            return "🤝 Day ends, no one is lynched. Night begins."
        target = top[0]
        victim = self.players[target]
        if victim.role is PRINCE and target not in self.prince_revealed:
            self.prince_revealed.add(target)
            self.phase = "day"
            self.day_votes.clear()
            return f"👑 {victim.name} rupanya Prince, batal undi, sambung malam."
        if victim.role is TANNER:
            self.phase = "over"
            return f"🟠 {victim.name} kena undi keluar, Tanner menang, GG."
        victim.alive = False
        self.wolf_cub_lynched_yesterday = (victim.role is WOLF_CUB)
        hunter_text = ""
        if victim.role is HUNTER:
            hunter_text = f" {victim.name} was the Hunter, the host may allow a final shot."
        self.phase = "day"
        self.day_votes.clear()
        winner = self.is_over()
        if winner:
            self.phase = "over"
            return f"📢 {victim.name} kena undi keluar. {winner}."
        return f"📢 {victim.name} kena undi keluar.{hunter_text} 🌙 Sambung malam."

    def resolve_night(self) -> str:
        if self.old_hag_target and self.players.get(self.old_hag_target, Player(0,"")).alive:
            self.silenced_today = {self.old_hag_target}
        else:
            self.silenced_today = set()

        kills: List[int] = []
        if not self.wolves_skip_kill_tonight and self.wolf_votes:
            tally: Dict[int, int] = {}
            for t in self.wolf_votes.values():
                tally[t] = tally.get(t, 0) + 1
            max_votes = max(tally.values())
            top = [t for t, v in tally.items() if v == max_votes]
            target = random.choice(top)
            kills.append(target)
        self.wolves_skip_kill_tonight = False

        protected: Set[int] = set()
        if self.doctor_target:
            protected.add(self.doctor_target)
        if self.bodyguard_target:
            protected.add(self.bodyguard_target)
            self.bodyguard_last_target = self.bodyguard_target
        if self.priest_target:
            protected.add(self.priest_target)

        if self.witch_heal_target is not None and self.witch_heal_available:
            kills = [k for k in kills if k != self.witch_heal_target]
            protected.add(self.witch_heal_target)
            self.witch_heal_available = False

        cult_converted: Optional[int] = None
        if self.cult_target is not None:
            t = self.players.get(self.cult_target)
            if t and t.alive:
                if t.user_id in protected or t.user_id in self.wolves or t.user_id in self.vampires:
                    pass
                else:
                    self.cult.add(t.user_id)
                    cult_converted = t.user_id

        vamp_converted: Optional[int] = None
        if self.vampire_target is not None:
            t = self.players.get(self.vampire_target)
            if t and t.alive:
                if t.user_id in protected:
                    pass
                else:
                    if t.role.alignment is Alignment.VILLAGE and t.role not in (PRIEST, SEER, APPRENTICE_SEER, AURA_SEER, BODYGUARD, WITCH, DOCTOR):
                        t.role = VAMPIRE
                        self.vampires.add(t.user_id)
                        vamp_converted = t.user_id
                    else:
                        t.alive = False
                        died = t.user_id
                        if died not in kills:
                            kills.append(died)

        died_tonight: List[int] = []
        diseased_killed = False
        for target in kills:
            if target in protected:
                continue
            victim = self.players.get(target)
            if not victim or not victim.alive:
                continue
            if victim.role is TOUGH_GUY:
                self.tough_guy_pending_death = target
                continue
            if victim.role is CURSED:
                victim.role = WEREWOLF
                self.wolves.add(victim.user_id)
                continue
            if victim.role is DISEASED:
                diseased_killed = True
            victim.alive = False
            died_tonight.append(target)

        if diseased_killed:
            self.wolves_skip_kill_tonight = True

        if self.witch_poison_target is not None and self.witch_poison_available:
            t = self.players.get(self.witch_poison_target)
            if t and t.alive and t.user_id not in protected:
                t.alive = False
                died_tonight.append(self.witch_poison_target)
            self.witch_poison_available = False

        if self.lovers:
            a, b = self.lovers
            a_dead = a in died_tonight or not self.players[a].alive
            b_dead = b in died_tonight or not self.players[b].alive
            if a_dead and self.players[b].alive:
                self.players[b].alive = False
                died_tonight.append(b)
            elif b_dead and self.players[a].alive:
                self.players[a].alive = False
                died_tonight.append(a)

        self.wolf_votes.clear()
        self.seer_target = None
        self.aura_target = None
        self.sorceress_target = None
        self.priest_target = None
        self.pii_first = None
        self.pii_second = None
        self.doctor_target = None
        self.bodyguard_target = None
        self.witch_heal_target = None
        self.witch_poison_target = None
        self.old_hag_target = None
        self.vampire_target = None
        self.cult_target = None

        self.last_killed = died_tonight[-1] if died_tonight else None
        self.phase = "day"
        self.day_votes.clear()
        self.day_count += 1

        parts = []
        if died_tonight:
            parts.append(f"💀 {', '.join(self.name_of(x) for x in died_tonight)} tumbang waktu malam.")
        if vamp_converted is not None:
            parts.append(f"🧛 {self.name_of(vamp_converted)} kena bite, jadi vampire geng.")
        if cult_converted is not None:
            parts.append(f"🔮 {self.name_of(cult_converted)} join cult, jangan bocor rahsia.")
        if not parts:
            parts.append("👍 Malam ni selamat, tak ada yang tumbang.")
        parts.append("🌞 Siang bermula, masa borak dan vote.")
        return " ".join(parts)
