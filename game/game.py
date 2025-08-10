
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
import random
from .roles import *

@dataclass
class PlayerState:
    user_id: int
    name: str
    role: Role = VILLAGER
    alive: bool = True

@dataclass
class Game:
    chat_id: int
    thread_id: int = 0

    host_id: Optional[int] = None
    phase: str = "lobby"  # lobby, day, night, end
    day: int = 0

    players: Dict[int, PlayerState] = field(default_factory=dict)  # uid -> PlayerState
    order: List[int] = field(default_factory=list)  # seating order

    # day
    votes: Dict[int, object] = field(default_factory=dict) # voter uid -> target uid or "skip"

    # night actions
    wolf_votes: Dict[int, int] = field(default_factory=dict)
    seer_target: Optional[int] = None
    aura_target: Optional[int] = None
    sorc_target: Optional[int] = None
    priest_target: Optional[int] = None
    doctor_target: Optional[int] = None
    bodyguard_target: Optional[int] = None
    witch_heal_target: Optional[int] = None
    witch_poison_target: Optional[int] = None
    vampire_target: Optional[int] = None
    cult_target: Optional[int] = None

    # resources
    witch_heal_available: bool = True
    witch_poison_available: bool = True
    bodyguard_last_target: Optional[int] = None

    # ui msg ids
    vote_msg_id: Optional[int] = None
    day_banner_id: Optional[int] = None

    # teams
    wolves: Set[int] = field(default_factory=set)
    vampires: Set[int] = field(default_factory=set)
    cult: Set[int] = field(default_factory=set)
    masons: Set[int] = field(default_factory=set)

    def add_player(self, uid:int, name:str) -> str:
        if uid in self.players:
            return "Already in lobby."
        self.players[uid] = PlayerState(uid, name)
        self.order.append(uid)
        return f"{name} joined."

    def assign_roles(self, deck: List[Role]) -> str:
        uids = list(self.players.keys())
        random.shuffle(uids)
        pool = list(deck)
        random.shuffle(pool)
        if len(pool) < len(uids):
            pool += [VILLAGER] * (len(uids)-len(pool))
        for uid, role in zip(uids, pool[:len(uids)]):
            ps = self.players[uid]
            ps.role = role
            # track teams
            if role in (WEREWOLF, WOLF_CUB, LONE_WOLF, MINION):
                self.wolves.add(uid)
            if role == MASON:
                self.masons.add(uid)
            if role == VAMPIRE:
                self.vampires.add(uid)
            if role == CULT_LEADER:
                self.cult.add(uid)
        self.phase = "day"
        self.day = 1
        self.votes.clear()
        # reset night actions
        self.wolf_votes.clear()
        self.seer_target = self.aura_target = self.sorc_target = self.priest_target = None
        self.doctor_target = self.bodyguard_target = None
        self.witch_heal_target = self.witch_poison_target = None
        self.vampire_target = self.cult_target = None
        return "🎬 Roles assigned. Check your DM."

    def list_alive_numbers(self) -> Dict[int,int]:
        # map uid -> number
        mapping = {}
        for i, uid in enumerate(self.order, start=1):
            if self.players[uid].alive:
                mapping[uid] = i
        return mapping

    def alive_list(self) -> List[int]:
        return [uid for uid in self.order if self.players[uid].alive]

    # --- Day voting ---
    def vote(self, voter:int, target:object) -> str:
        if self.phase != "day": return "Not day."
        if voter not in self.players or not self.players[voter].alive: return "You are not alive."
        if target!="skip" and (target not in self.players or not self.players[target].alive): return "Invalid target."
        self.votes[voter] = target
        return "Vote recorded."

    def tally(self) -> Tuple[Optional[int], bool]:
        # returns, target uid or None, and whether tie/skip
        counts={}
        for tgt in self.votes.values():
            counts[tgt]=counts.get(tgt,0)+1
        if not counts: return None, True
        # find max
        mx = max(counts.values())
        winners=[t for t,n in counts.items() if n==mx]
        if len(winners)>1: return None, True
        winner = winners[0]
        if winner=="skip": return None, True
        return int(winner), False

    # --- Night actions ---
    def wolf_kill(self, uid:int, target:int) -> str:
        if self.phase!="night": return "Not night."
        if uid not in self.wolves: return "Not a wolf."
        if target not in self.alive_list(): return "Invalid target."
        self.wolf_votes[uid]=target
        return "Wolf vote recorded."

    def seer_peek(self, uid:int, target:int) -> str:
        if self.phase!="night": return "Not night."
        if self.players[uid].role!=SEER: return "Not Seer."
        self.seer_target=target; return "Seen."

    def aura_peek(self, uid:int, target:int) -> str:
        if self.phase!="night": return "Not night."
        if self.players[uid].role!=AURA_SEER: return "Not Aura Seer."
        self.aura_target=target; return "Aura read."

    def sorceress_scry(self, uid:int, target:int) -> str:
        if self.phase!="night": return "Not night."
        if self.players[uid].role!=SORCERESS: return "Not Sorceress."
        self.sorc_target=target; return "Scry set."

    def priest_bless(self, uid:int, target:int) -> str:
        if self.phase!="night": return "Not night."
        if self.players[uid].role!=PRIEST: return "Not Priest."
        self.priest_target=target; return "Bless set."

    def doctor_save(self, uid:int, target:int) -> str:
        if self.phase!="night": return "Not night."
        if self.players[uid].role!=DOCTOR: return "Not Doctor."
        self.doctor_target=target; return "Save set."

    def bodyguard_protect(self, uid:int, target:int) -> str:
        if self.phase!="night": return "Not night."
        if self.players[uid].role!=BODYGUARD: return "Not Bodyguard."
        self.bodyguard_target=target; return "Protect set."

    def witch_heal(self, uid:int, target:int) -> str:
        if self.phase!="night": return "Not night."
        if self.players[uid].role!=WITCH or not self.witch_heal_available: return "Cannot heal."
        self.witch_heal_target=target; return "Heal used."

    def witch_poison(self, uid:int, target:int) -> str:
        if self.phase!="night": return "Not night."
        if self.players[uid].role!=WITCH or not self.witch_poison_available: return "Cannot poison."
        self.witch_poison_target=target; return "Poison set."

    def vampire_bite(self, uid:int, target:int) -> str:
        if self.phase!="night": return "Not night."
        if self.players[uid].role!=VAMPIRE: return "Not Vampire."
        self.vampire_target=target; return "Bite set."

    def cult_recruit(self, uid:int, target:int) -> str:
        if self.phase!="night": return "Not night."
        if self.players[uid].role!=CULT_LEADER: return "Not Cult Leader."
        self.cult_target=target; return "Recruit set."

    # --- Phase resolution ---
    def resolve_day(self) -> str:
        target, tie = self.tally()
        self.votes.clear()
        if tie or target is None:
            self.phase="night"
            return "📢 Hari tamat, tiada lynch. 🌙 Malam bermula."
        # lynch target
        self.players[target].alive=False
        self.phase="night"
        return f"📢 Hari tamat, {self.players[target].name} digantung. 🌙 Malam bermula."

    def resolve_night(self) -> str:
        victims=[]
        # wolf kill by plurality
        if self.wolf_votes:
            tally={}
            for t in self.wolf_votes.values():
                tally[t]=tally.get(t,0)+1
            wolf_target = max(tally, key=tally.get)
        else:
            wolf_target=None

        saved=set()
        if self.doctor_target: saved.add(self.doctor_target)
        if self.bodyguard_target:
            saved.add(self.bodyguard_target)
            self.bodyguard_last_target=self.bodyguard_target

        # witch heal overrides, if set
        if self.witch_heal_target: saved.add(self.witch_heal_target)
        # apply wolf kill
        if wolf_target and wolf_target not in saved and self.players.get(wolf_target, None) and self.players[wolf_target].alive:
            victims.append(wolf_target)

        # witch poison death
        if self.witch_poison_target and self.players.get(self.witch_poison_target, None) and self.players[self.witch_poison_target].alive:
            victims.append(self.witch_poison_target)

        # vampire converts, not kill
        if self.vampire_target and self.players.get(self.vampire_target, None) and self.players[self.vampire_target].alive:
            self.vampires.add(self.vampire_target)

        # cult recruit
        if self.cult_target and self.players.get(self.cult_target, None) and self.players[self.cult_target].alive:
            self.cult.add(self.cult_target)

        # mark deaths
        unique_victims=[]
        for v in victims:
            if v not in unique_victims:
                unique_victims.append(v)
        for v in unique_victims:
            self.players[v].alive=False

        # reset night actions
        self.wolf_votes.clear()
        self.seer_target=self.aura_target=self.sorc_target=self.priest_target=None
        self.doctor_target=self.bodyguard_target=None
        self.witch_heal_target=self.witch_poison_target=None
        self.vampire_target=self.cult_target=None

        self.phase="day"; self.day+=1

        if unique_victims:
            names=", ".join(self.players[v].name for v in unique_victims)
            return f"🌙 Malam berakhir. 💀 Tumbang, {names}. 🌞 Day {self.day} bermula."
        else:
            return f"🌙 Malam berakhir. 👍 Tiada kematian. 🌞 Day {self.day} bermula."
