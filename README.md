Phase 4, presets and role toggles, JSON upload, auto summaries.

New group commands
- /preset name, classic, social, chaos, cult
- /showroles, list current roles for next game
- /addrole RoleName, add one copy, /removerole RoleName, remove one copy
- /setrolesjson <json>, paste a list or a {name:count} map
- Send a roles.json file, the bot reads it and sets the list

Auto summaries
- After /day, posts a night summary
- After /endday, posts a day summary

roles.json formats
- List, ["Villager","Werewolf","Seer","Doctor","Witch","Bodyguard"]
- Map, {"Villager":6,"Werewolf":2,"Seer":1,"Doctor":1,"Witch":1,"Bodyguard":1}

Deploy the same way as Phase 3.
