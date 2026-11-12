from http.client import HTTPResponse

import urllib.parse
import urllib.request
import urllib.error

import json
import time
import os
import traceback 
import base64
import math

from eggdrop import bind
from eggdrop.tcl import putmsg, putlog, putdcc




# Attempt to import client and secret via .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_TOKEN_CACHE = {"access_token": None, "expires_at": 0}
MAX_LEVEL = 60


FOREVER_XP_TABLE = {
    1: 400, 2: 900, 3: 1400, 4: 2100, 5: 2800, 6: 3600, 7: 4500, 8: 5400, 9: 6500, 10: 7600,
    11: 8800, 12: 10100, 13: 11400, 14: 12900, 15: 14400, 16: 16000, 17: 17700, 18: 19400, 19: 21300, 20: 23200,
    21: 25200, 22: 27300, 23: 29400, 24: 31700, 25: 34000, 26: 36400, 27: 38900, 28: 41400, 29: 44300, 30: 47400,
    31: 50800, 32: 54500, 33: 58600, 34: 62800, 35: 67100, 36: 71600, 37: 76100, 38: 80800, 39: 85700, 40: 90700,
    41: 95800, 42: 101000, 43: 106300, 44: 111800, 45: 117500, 46: 123200, 47: 129100, 48: 135100, 49: 141200, 50: 147500,
    51: 153900, 52: 160400, 53: 167100, 54: 173900, 55: 180800, 56: 187900, 57: 195000, 58: 202300, 59: 209800
}



"""
***----------------------------------------------------------------------------
*** User Configuration ***
***>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
""" 
### YOU MUST CONFIGURE YOUR API CLIENT &SECRET KEYS OR THE SCRIPT WILL NOT WORK!
MY_CLIENT_ID = "YOUR_CLIENT_ID_HERE"
MY_SECRET = "YOUR_SECRET_KEY_HERE"
CLIENT_ID = os.getenv("BLIZZARD_CLIENT_ID", MY_CLIENT_ID )
CLIENT_SECRET = os.getenv("BLIZZARD_CLIENT_SECRET", MY_SECRET)



WOWHEAD_BASE_URL = "https://wowhead.com"

"""
***----------------------------------------------------------------------------
*** AUTHENTICATION / TOKEN MANAGEMENT
***>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
"""



def get_valid_blizzard_token() -> str:
    """ Returns cached token or fetches new one"""
    now = time.time()

    if _TOKEN_CACHE["access_token"] and now < _TOKEN_CACHE["expires_at"]:
        return _TOKEN_CACHE["access_token"]

    # Otherwise, perform the HTTP POSTto fetch a new token
    url = "https://oauth.battle.net/token"
    data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    auth_str = f"{CLIENT_ID}:{CLIENT_SECRET}"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    req.add_header("Authorization", f"Basic {b64_auth}")

    # Make the network request
    with urllib.request.urlopen(req) as response:
        resp: HTTPResponse = response
        res = json.loads(resp.read().decode())

        token = res.get("access_token")

        #Blizzard returns expiration in seconds (default 86400 / 24 hrs)
        expires_in = res.get("expires_in", 86400)

        # Cache token and set expiration timestamp (with 5-min buffer)
        _TOKEN_CACHE["access_token"] = token
        _TOKEN_CACHE["expires_at"] = now +expires_in - 300

        putlog("Fetched fresh Blizzard API token.")
        return token


def to_wowhead_version(version: str) -> str:
    if version == "tbc":
        return "tbc"
    elif version == "era":
        return "classic"
    elif version == "mop":
        return "mop-classic"
    elif version == "forever":
        return "forever"
    else:
        return "invalid"

def get_wowhead_item_link(id: str, version: str) -> str:
    ver = to_wowhead_version(version)
    if ver == "invalid":
        return "invalid"
    return f"{WOWHEAD_BASE_URL}/{ver}/item={id}"


def get_wowhead_creature_link(id: str, version: str) -> str:
    ver = to_wowhead_version(version)
    return f"{WOWHEAD_BASE_URL}/{ver}/npc={id}/"


def is_valid_version(version: str) -> bool:
    VALID_VERSIONS = { "era", "tbc", "mop", "forever" }

    return version in VALID_VERSIONS

def format_with_gold(copper_in) -> str :
    gold = copper_in // 10_000
    silver = copper_in % 10_000 // 100
    copper = copper_in % 100
    return f"{gold}g {silver}s {copper}c"

def format_slug(name: str) -> str:
    cleaned = name.strip().lower().replace(' ', '-').replace("'", "")
    # Percent-encode Unicode characters (e.g. 'ö' becomes '%C3%B6')
    return urllib.parse.quote(cleaned)

def get_xp_progress(level: int, current_xp: int) -> str:
    

    if level >= MAX_LEVEL:
        return "Max Level"

    needed_xp = FOREVER_XP_TABLE.get(level)

    if not needed_xp:
        return "Unknown"

    pct = math.ceil((current_xp / needed_xp) * 100)
    return f"{pct:.1f}%"


"""
***----------------------------------------------------------------------------
*** DATA & API FUNCTIONS
***>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
"""

def get_character_data(access_token: str, first_name: str, last_name: str,
                       region="us", locale="en_US") -> dict :
    
    
    
    char_name = f"{format_slug(first_name)}-{format_slug(last_name)}"
    namespace = f"profile-forever-{region}"

    url = f"https://{region}.api.blizzard.com/profile/wow/character/{char_name}?namespace={namespace}&locale={locale}"
    

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")

    try:
        with urllib.request.urlopen(req) as response:
            data =json.loads(response.read().decode())

            name = data.get("name", char_name)
            level = data.get("level", 0)
            race = data.get("race", {}).get("name", "Unknown Race")
            cls = data.get("character_class", {}).get("name", "Unknown Class")
            #realm_name = data.get("realm", {}).get("name", realm.capitalize())
            faction = data.get("faction", {}).get("name", "Unknown Faction")
            ilvl = data.get("equipped_item_level", 0)
            gender = data.get("gender", {}).get("name", "Unknown Gender")
            xp_progress_pct = get_xp_progress(level, data.get("experience", 0))

            # Guild is omitted from JSON if player is unguilded
            guild_info = ""
            if "guild" in data:
                guild_name = data["guild"].get("name")
                if guild_name:
                    guild_info = f" | Guild: <{guild_name}>"

            return {
                "name": name,
                "level": level,
                "race": race,
                "class": cls,
                "faction": faction,
                "ilvl": ilvl,
                "gender": gender,
                "guild": guild_info,
                "version": "forever",
                "xp_progress_pct": xp_progress_pct
            }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": f"Character '{char_name}' not found."}
        return {"error": f"HTTP Error fetching character: {e.code}"}

def get_character_equipment(access_token: str, first_name: str, last_name: str, region="us", locale="en_US") -> dict:
    char_slug = format_slug(f"{first_name}-{last_name}")
    namespace = f"profile-forever-{region}"

    url = f"https://{region}.api.blizzard.com/profile/wow/character/{char_slug}/equipment?namespace={namespace}&locale={locale}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")

    try:
        with urllib.request.urlopen(req) as response:
            response: HTTPResponse = response
            data = json.loads(response.read().decode())
            equip_data: list[dict[str, Any]]= data.get("equipped_items", [])

            if not equip_data:
                return {"error": "No equipment data found"}
            
            equipment = [
                {
                    "slot": piece.get("slot", {}).get("name", "Slot"),
                    "name": piece.get("name", "Unknown Item")
                }
                for piece in equip_data
            ]


            return {
                "character": f"{first_name} {last_name}",
                "version": "forever",
                "equipment": equipment
            }
        
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": f"Character '{first_name} {last_name}' not found."}
        return {"error": f"HTTP Error fetching character: {e.code}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}

"""
***----------------------------------------------------------------------------
*** TCL PUBLIC BIND FUNCTIONS
***>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
"""

def pub_get_character_gear(nick: str, user: str, hand: str, chan: str, text: str,
                     **kwargs):
    try:
        query = text.strip()
        if not query:
            putmsg(chan, "Usage !gear <first_name> <last_name>")
            return

        query = query.split()
        arg_count = len(query)
        if arg_count != 2:
                putmsg(chan, "Usage !gear <first_name> <last_name>")
                return
        else:
            first_name, last_name = query
        
        putlog(f"[Forever] Gear Lookup <{nick}> {chan} - {first_name} {last_name}")

        token = get_valid_blizzard_token()
        equipment = get_character_equipment(token, first_name, last_name)


        for line in format_character_equipment_irc(equipment):
            putmsg(chan, line)

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching player gear data.")


def pub_get_character_summary(nick: str, user: str, hand: str, chan: str, text: str,
                     **kwargs):
    try:
        query = text.strip()
        if not query:
            putmsg(chan, "Usage: !character <first_name> <last_name>")
            return

        query = query.split()
        arg_count = len(query)
        if arg_count < 2:
                putmsg(chan, "Usage: !character <first_name> <last_name>")
                return
        first_name, last_name = query

        
        putlog(f"Character lookup <{nick}> on {chan} - {first_name} {last_name}")

        token = get_valid_blizzard_token()
        character_info = get_character_data(token, first_name, last_name)

        putmsg(chan, f"[Forever] {format_character_info_irc(character_info)}")

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching player character data.")

"""
***----------------------------------------------------------------------------
*** IRC FORMATTING FUNCTIONS
***>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
"""

def format_character_equipment_irc(data: dict) -> list[str]:
    if not data or "error" in data:
        return [data.get("error", "Error: Invalid equipment data.")]
    
    equipment = data.get("equipment")
    if not equipment:
        return ["No equipment items found."]
    
    items = [f"{item['slot']}: {item['name']}" for item in equipment]

    # Pack items into lines under 350 characters for IRC buffers
    lines = []
    current_line = []
    current_len = 0
    MAX_LEN = 350

    for item in items:
        # 3 accounts for the " | " separator
        added_len = len(item) + (3 if current_line else 0)
        if current_len + added_len > MAX_LEN:
            lines.append(" | ".join(current_line))
            current_line = [item]
            current_len = len(item)
        else:
            current_line.append(item)
            current_len += added_len

    if current_line:
        lines.append(" | ".join(current_line))

    return lines

def format_character_info_irc(info: dict) -> str:
    if not info or "error" in info:
        return "Error: Invalid character data."

    return f"{info['name']} ({info['gender']}) Lvl {info['level']} ({info['xp_progress_pct']}) {info['race']} {info['class']} | Faction: {info['faction']} | iLvl: {info['ilvl']}{info['guild']}"



if 'WOW_BINDS' in globals(): 
    for wbind in WOW_BINDS:
        wbind.unbind()
    del WOW_BINDS


WOW_BINDS = list()

# Public commands
WOW_BINDS.append(bind("pub", "-", "!character", pub_get_character_summary))
WOW_BINDS.append(bind("pub", "-", "!gear", pub_get_character_gear))


# Dcc commands
#WOW_BINDS.append(bind("dcc", "-", "item", dcc_get_item_info))


putlog("Loaded forever.py!")
