from dataclasses import dataclass
from enum import Enum, auto

class Alignment(Enum):
    VILLAGE = auto()
    WOLF = auto()
    NEUTRAL = auto()

@dataclass
class Role:
    name: str
    alignment: Alignment
    night_action: bool = False

# Core
VILLAGER = Role("Villager", Alignment.VILLAGE, night_action=False)
WEREWOLF = Role("Werewolf", Alignment.WOLF, night_action=True)
SEER = Role("Seer", Alignment.VILLAGE, night_action=True)
DOCTOR = Role("Doctor", Alignment.VILLAGE, night_action=True)

# Big set
WITCH = Role("Witch", Alignment.VILLAGE, night_action=True)
CUPID = Role("Cupid", Alignment.VILLAGE, night_action=True)
TOUGH_GUY = Role("Tough Guy", Alignment.VILLAGE, night_action=False)
BODYGUARD = Role("Bodyguard", Alignment.VILLAGE, night_action=True)
HUNTER = Role("Hunter", Alignment.VILLAGE, night_action=False)
PRINCE = Role("Prince", Alignment.VILLAGE, night_action=False)
MASON = Role("Mason", Alignment.VILLAGE, night_action=False)
MINION = Role("Minion", Alignment.WOLF, night_action=False)
WOLF_CUB = Role("Wolf Cub", Alignment.WOLF, night_action=True)
OLD_HAG = Role("Old Hag", Alignment.VILLAGE, night_action=True)
SPELLCASTER = Role("Spellcaster", Alignment.VILLAGE, night_action=True)
PACIFIST = Role("Pacifist", Alignment.VILLAGE, night_action=False)
GHOST = Role("Ghost", Alignment.VILLAGE, night_action=False)

APPRENTICE_SEER = Role("Apprentice Seer", Alignment.VILLAGE, night_action=False)
AURA_SEER = Role("Aura Seer", Alignment.VILLAGE, night_action=True)
LYCAN = Role("Lycan", Alignment.VILLAGE, night_action=False)
CURSED = Role("Cursed", Alignment.VILLAGE, night_action=False)
DISEASED = Role("Diseased", Alignment.VILLAGE, night_action=False)
MAYOR = Role("Mayor", Alignment.VILLAGE, night_action=False)
HOODLUM = Role("Hoodlum", Alignment.NEUTRAL, night_action=False)
PRIEST = Role("Priest", Alignment.VILLAGE, night_action=True)
PARANORMAL_INV = Role("Paranormal Investigator", Alignment.VILLAGE, night_action=True)
SORCERESS = Role("Sorceress", Alignment.WOLF, night_action=True)
TROUBLEMAKER = Role("Troublemaker", Alignment.VILLAGE, night_action=True)
VAMPIRE = Role("Vampire", Alignment.NEUTRAL, night_action=True)
VILLAGE_IDIOT = Role("Village Idiot", Alignment.VILLAGE, night_action=False)
TANNER = Role("Tanner", Alignment.NEUTRAL, night_action=False)
LONE_WOLF = Role("Lone wolf", Alignment.WOLF, night_action=True)

CULT_LEADER = Role("Cult Leader", Alignment.NEUTRAL, night_action=True)

ALL_ROLES = [
    VILLAGER, WEREWOLF, SEER, DOCTOR, WITCH, CUPID, TOUGH_GUY, BODYGUARD, HUNTER, PRINCE,
    MASON, MINION, WOLF_CUB, OLD_HAG, SPELLCASTER, PACIFIST, GHOST,
    APPRENTICE_SEER, AURA_SEER, LYCAN, CURSED, DISEASED, MAYOR, HOODLUM, PRIEST, PARANORMAL_INV,
    SORCERESS, TROUBLEMAKER, VAMPIRE, VILLAGE_IDIOT, TANNER, LONE_WOLF, CULT_LEADER
]

ROLE_BY_NAME = {r.name.lower(): r for r in ALL_ROLES}
