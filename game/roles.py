
from enum import Enum, auto
from dataclasses import dataclass

class Alignment(Enum):
    VILLAGE = auto()
    WOLF = auto()
    NEUTRAL = auto()

@dataclass(frozen=True)
class Role:
    name: str
    alignment: Alignment
    has_night_action: bool = False

# Core action roles
WEREWOLF = Role("Werewolf", Alignment.WOLF, True)
WOLF_CUB = Role("Wolf Cub", Alignment.WOLF, True)
LONE_WOLF = Role("Lone Wolf", Alignment.WOLF, True)

SEER = Role("Seer", Alignment.VILLAGE, True)
AURA_SEER = Role("Aura Seer", Alignment.VILLAGE, True)
SORCERESS = Role("Sorceress", Alignment.NEUTRAL, True)
PRIEST = Role("Priest", Alignment.VILLAGE, True)

BODYGUARD = Role("Bodyguard", Alignment.VILLAGE, True)
DOCTOR = Role("Doctor", Alignment.VILLAGE, True)
WITCH = Role("Witch", Alignment.VILLAGE, True)

VAMPIRE = Role("Vampire", Alignment.NEUTRAL, True)
CULT_LEADER = Role("Cult Leader", Alignment.NEUTRAL, True)

# Passive or social roles
APPRENTICE_SEER = Role("Apprentice Seer", Alignment.VILLAGE, False)
CUPID = Role("Cupid", Alignment.VILLAGE, False)
CURSED = Role("Cursed", Alignment.VILLAGE, False)
DISEASED = Role("Diseased", Alignment.VILLAGE, False)
DOPPELGANGER = Role("Doppelganger", Alignment.NEUTRAL, False)
DRUNK = Role("Drunk", Alignment.VILLAGE, False)
GHOST = Role("Ghost", Alignment.NEUTRAL, False)
HOODLUM = Role("Hoodlum", Alignment.NEUTRAL, False)
HUNTER = Role("Hunter", Alignment.VILLAGE, False)
LUCID_LYCAN = Role("Lycan", Alignment.VILLAGE, False)
MASON = Role("Mason", Alignment.VILLAGE, False)
MAYOR = Role("Mayor", Alignment.VILLAGE, False)
MINION = Role("Minion", Alignment.WOLF, False)
OLD_HAG = Role("Old Hag", Alignment.VILLAGE, False)
PARANORMAL_INVESTIGATOR = Role("Paranormal Investigator", Alignment.VILLAGE, False)
PACIFIST = Role("Pacifist", Alignment.VILLAGE, False)
PRINCE = Role("Prince", Alignment.VILLAGE, False)
SPELLCASTER = Role("Spellcaster", Alignment.VILLAGE, False)
TANNER = Role("Tanner", Alignment.NEUTRAL, False)
TOUGH_GUY = Role("Tough Guy", Alignment.VILLAGE, False)
TROUBLEMAKER = Role("Troublemaker", Alignment.NEUTRAL, False)
VILLAGE_IDIOT = Role("Village Idiot", Alignment.VILLAGE, False)
VILLAGER = Role("Villager", Alignment.VILLAGE, False)

ALL_ROLES = [
    SEER, APPRENTICE_SEER, AURA_SEER, BODYGUARD, CULT_LEADER,
    CUPID, CURSED, DISEASED, DOPPELGANGER, DRUNK,
    GHOST, HOODLUM, HUNTER, LONE_WOLF, LUCID_LYCAN,
    MASON, MAYOR, MINION, OLD_HAG, PARANORMAL_INVESTIGATOR,
    PACIFIST, PRIEST, PRINCE, SORCERESS, SPELLCASTER,
    TANNER, TOUGH_GUY, TROUBLEMAKER, VAMPIRE, VILLAGE_IDIOT,
    VILLAGER, WEREWOLF, WITCH, WOLF_CUB
]
