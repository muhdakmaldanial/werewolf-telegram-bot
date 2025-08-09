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

    # Night actions subset, representative, enough for buttons feature
    def wolf_vote(self, voter_id: int, target_id: int) -> str:
        if self.phase != "night":
            return "It is not night."
        actor = self.players.get(voter_id)
        if not actor or not actor.alive or actor.role not in (WEREWOLF, WOLF_CUB, LONE_WOLF):
            return "Only living wolves can vote at night."
        if target_id not in self.players or not self.players[target_id].alive:
            return "Invalid target."
        if voter_id in self.bound_next_night:
            return "You are bound and cannot act this night."
        self.wolf_votes[voter_id] = target_id
        return f"Wolf vote recorded on {self.name_of(target_id)}."

    def doctor_save(self, doctor_id: int, target_id: int) -> str:
        if self.phase != "night":
            return "It is not night."
        d = self.players.get(doctor_id)
        if not d or not d.alive or d.role is not DOCTOR:
            return "Only the Doctor can save."
        if target_id not in self.players or not self.players[target_id].alive:
            return "Invalid target."
        if doctor_id in self.bound_next_night:
            return "You are bound and cannot act this night."
        self.doctor_target = target_id
        return f"Doctor will save {self.name_of(target_id)}."

    def seer_peek(self, seer_id: int, target_id: int) -> str:
        if self.phase != "night":
            return "It is not night."
        seer = self.players.get(seer_id)
        if not seer or not seer.alive or seer.role is not SEER:
            return "Only the Seer can use peek at night."
        if target_id not in self.players or not self.players[target_id].alive:
            return "Invalid target."
        if seer_id in self.bound_next_night:
            return "You are bound and cannot act this night."
        target = self.players[target_id]
        return f"{target.name} is {self.alignment_for_seer(target)}."

    def aura_peek(self, aura_id: int, target_id: int) -> str:
        if self.phase != "night":
            return "It is not night."
        a = self.players.get(aura_id)
        if not a or not a.alive or a.role is not AURA_SEER:
            return "Only the Aura Seer can act."
        if target_id not in self.players or not self.players[target_id].alive:
            return "Invalid target."
        if aura_id in self.bound_next_night:
            return "You are bound and cannot act this night."
        t = self.players[target_id]
        return f"{t.name} has {self.aura_for_aura_seer(t)}."

    def priest_bless(self, priest_id: int, target_id: int) -> str:
        if self.phase != "night":
            return "It is not night."
        p = self.players.get(priest_id)
        if not p or not p.alive or p.role is not PRIEST:
            return "Only the Priest can bless."
        if target_id not in self.players or not self.players[target_id].alive:
            return "Invalid target."
        if priest_id in self.bound_next_night:
            return "You are bound and cannot act this night."
        self.priest_target = target_id
        return f"Priest will bless {self.name_of(target_id)}."

    def sorceress_scry(self, sorc_id: int, target_id: int) -> str:
        if self.phase != "night":
            return "It is not night."
        s = self.players.get(sorc_id)
        if not s or not s.alive or s.role is not SORCERESS:
            return "Only the Sorceress can act."
        if target_id not in self.players or not self.players[target_id].alive:
            return "Invalid target."
        if sorc_id in self.bound_next_night:
            return "You are bound and cannot act this night."
        t = self.players[target_id]
        is_seer = t.role in (SEER, APPRENTICE_SEER, AURA_SEER)
        return f"{t.name} is {'a Seer type' if is_seer else 'not a Seer type'}."

    def vampire_bite(self, vamp_id: int, target_id: int) -> str:
        if self.phase != "night":
            return "It is not night."
        v = self.players.get(vamp_id)
        if not v or not v.alive or v.role is not VAMPIRE:
            return "Only the Vampire can act."
        if target_id not in self.players or not self.players[target_id].alive:
            return "Invalid target."
        if vamp_id in self.bound_next_night:
            return "You are bound and cannot act this night."
        self.vampire_target = target_id
        return f"Vampire will bite {self.name_of(target_id)}."

    def cult_recruit(self, leader_id: int, target_id: int) -> str:
        if self.phase != "night":
            return "It is not night."
        if leader_id not in self.players or self.players[leader_id].role is not CULT_LEADER or not self.players[leader_id].alive:
            return "Only the Cult Leader can recruit."
        if target_id not in self.players or not self.players[target_id].alive:
            return "Invalid target."
        if target_id in self.cult:
            return "That player is already in the cult."
        self.cult_target = target_id
        return f"Cult Leader will try to recruit {self.name_of(target_id)}."

    def bodyguard_protect(self, bg_id: int, target_id: int) -> str:
        if self.phase != "night":
            return "It is not night."
        bg = self.players.get(bg_id)
        if not bg or not bg.alive or bg.role is not BODYGUARD:
            return "Only the Bodyguard can protect."
        if target_id not in self.players or not self.players[target_id].alive:
            return "Invalid target."
        if bg_id in self.bound_next_night:
            return "You are bound and cannot act this night."
        if self.bodyguard_last_target == target_id:
            return "Cannot protect the same target twice in a row."
        self.bodyguard_target = target_id
        return f"Bodyguard will protect {self.name_of(target_id)}."

    def witch_heal(self, witch_id: int, target_id: int) -> str:
        if self.phase != "night":
            return "It is not night."
        w = self.players.get(witch_id)
        if not w or not w.alive or w.role is not WITCH:
            return "Only the Witch can use potions."
        if witch_id in self.bound_next_night:
            return "You are bound and cannot act this night."
        if not self.witch_heal_available:
            return "Heal potion already used."
        self.witch_heal_target = target_id
        return f"Witch will heal {self.name_of(target_id)}."

    def witch_poison(self, witch_id: int, target_id: int) -> str:
        if self.phase != "night":
            return "It is not night."
        w = self.players.get(witch_id)
        if not w or not w.alive or w.role is not WITCH:
            return "Only the Witch can use potions."
        if witch_id in self.bound_next_night:
            return "You are bound and cannot act this night."
        if not self.witch_poison_available:
            return "Poison already used."
        if target_id not in self.players or not self.players[target_id].alive:
            return "Invalid target."
        self.witch_poison_target = target_id
        return f"Witch will poison {self.name_of(target_id)}."

    def old_hag_silence(self, hag_id: int, target_id: int) -> str:
        if self.phase != "night":
            return "It is not night."
        h = self.players.get(hag_id)
        if not h or not h.alive or h.role is not OLD_HAG:
            return "Only the Old Hag can silence."
        if hag_id in self.bound_next_night:
            return "You are bound and cannot act this night."
        self.old_hag_target = target_id
        return f"Old Hag will silence {self.name_of(target_id)} tomorrow."

    def resolve_night(self) -> str:
        # Bind and silence
        if self.old_hag_target and self.players.get(self.old_hag_target, Player(0,"")).alive:
            self.silenced_today = {self.old_hag_target}
        else:
            self.silenced_today = set()

        # Tally wolf kill
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

        # Witch heal
        if self.witch_heal_target is not None and self.witch_heal_available:
            kills = [k for k in kills if k != self.witch_heal_target]
            protected.add(self.witch_heal_target)
            self.witch_heal_available = False

        # Cult conversion
        cult_converted: Optional[int] = None
        if self.cult_target is not None:
            t = self.players.get(self.cult_target)
            if t and t.alive:
                if t.user_id in protected or t.user_id in self.wolves or t.user_id in self.vampires:
                    pass
                else:
                    self.cult.add(t.user_id)
                    cult_converted = t.user_id

        # Vampire action, simplified, convert some village roles, else kill
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
                        kills.append(t.user_id)

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

        # reset night state
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
            parts.append(f"{', '.join(self.name_of(x) for x in died_tonight)} died last night.")
        if vamp_converted is not None:
            parts.append(f"{self.name_of(vamp_converted)} was turned by the Vampire.")
        if cult_converted is not None:
            parts.append(f"{self.name_of(cult_converted)} joined the Cult.")
        if not parts:
            parts.append("No one died last night.")
        parts.append("Day begins.")
        return " ".join(parts)

    # Day voting
    def vote(self, voter_id: int, target_id: int) -> str:
        if self.phase != "day":
            return "It is not day."
        if voter_id not in self.players or not self.players[voter_id].alive:
            return "Only living players can vote."
        if target_id not in self.players or not self.players[target_id].alive:
            return "Invalid target."
        if voter_id in self.silenced_today:
            return "You are silenced and cannot vote today."
        self.day_votes[voter_id] = target_id
        return f"Vote recorded on {self.name_of(target_id)}."

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
            self.phase = "night"
            return "No votes, night begins."

        max_votes = max(tally.values())
        top = [t for t, v in tally.items() if v == max_votes]

        if len(top) > 1 or max_votes == 0:
            self.phase = "night"
            return "Tie, no one is lynched. Night begins."

        target = top[0]
        victim = self.players[target]

        if victim.role is PRINCE and target not in self.prince_revealed:
            self.prince_revealed.add(target)
            self.phase = "night"
            self.day_votes.clear()
            return f"{victim.name} is the Prince, lynch cancelled. Night begins."

        if victim.role is TANNER:
            self.phase = "over"
            return f"{victim.name} was lynched. Tanner wins."

        victim.alive = False
        self.wolf_cub_lynched_yesterday = (victim.role is WOLF_CUB)

        hunter_text = ""
        if victim.role is HUNTER:
            hunter_text = f" {victim.name} was the Hunter, the host may allow a final shot."

        self.phase = "night"
        self.day_votes.clear()
        winner = self.is_over()
        if winner:
            self.phase = "over"
            return f"{victim.name} was lynched. {winner}."
        return f"{victim.name} was lynched.{hunter_text} Night begins."
