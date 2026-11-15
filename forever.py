from http.client import HTTPResponse
from typing import Any

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
VERSION = "forever"

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

def get_wowhead_item_link(id: str) -> str:
    return f"{WOWHEAD_BASE_URL}/{VERSION}/item={id}"


def get_wowhead_creature_link(id: str) -> str:
    return f"{WOWHEAD_BASE_URL}/{VERSION}/npc={id}/"


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
    namespace = f"profile-{VERSION}-{region}"

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
    namespace = f"profile-{VERSION}-{region}"

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


def search_creatures(access_token: str, creature: str, max_results=10,
                     region="us", locale="en_US") -> dict:

    query = urllib.parse.quote(creature)
    
    namespace = f"static-{VERSION}-{region}"

    url = f"https://{region}.api.blizzard.com/data/wow/search/creature?namespace={namespace}&name.{locale}={query}&orderby=id&_page=1&locale={locale}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")

    search_terms = creature.lower().split()
    creatures_found = []

    try:
        with urllib.request.urlopen(req) as response:
            response: HTTPResponse = response
            data: dict[str, Any] = json.loads(response.read().decode())

            results = data.get("results", [])

            if not results:
                return {"error": "No creatures found."}

            for item in results:
                data = item.get("data", {})
                id = data.get("id")
                name = data.get("name", {}).get(locale, "Unknown")

                if id and all(term in name.lower() for term in search_terms):
                    creatures_found.append({"id": id, "name": name})
                if len(creatures_found) > max_results:
                    break

            return {
                "query": query,
                "results": creatures_found
            } 
    
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": "Error: Creature search API endpoint not found."}
        return {"error": f"HTTP Error fetching creature data: {e.code}"}
    except Exception as e:
        return {"error": str(e)}


def get_creature_data(access_token: str, creature_id: str, region="us", locale="en_US") -> dict:
    
    namespace = f"static-{VERSION}-{region}"

    url = f"https://{region}.api.blizzard.com/data/wow/creature/{creature_id}?namespace={namespace}&locale={locale}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")

    try:
        with urllib.request.urlopen(req) as response:
            response: HTTPResponse = response

            data: dict[str, Any] = json.loads(response.read().decode())

            c_id = data.get("id", creature_id)
            c_name = data.get("name", "Unknown")
            t_name = data.get("type", {}).get("name", "Unknown")
            family = data.get("family", {}).get("name", "Unknown")
            tameable = "Yes" if data.get("is_tameable") else "No"
            wowhead_url = get_wowhead_creature_link(creature_id)

            return {
                "id": c_id,
                "name": c_name,
                "type": t_name,
                "family": family,
                "tameable": tameable,
                "wowhead_url": wowhead_url
            }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error":"Error: Creature not found."}
        return {"error": f"HTTP Error fetching creature: {e.code}"}

def get_item_data(access_token: str, item_id: str, region="us", locale="en_US") -> dict :
    
    namespace = f"static-{VERSION}-{region}"
    url = f"https://{region}.api.blizzard.com/data/wow/item/{item_id}?namespace={namespace}&locale={locale}"

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")

    try:
        with urllib.request.urlopen(req) as response:
            resp: HTTPResponse = response
            data: dict[str, Any] = json.loads(resp.read().decode())

            name = data.get("name", "Unknown Item")
            level = data.get("level", 0)
            id = data.get("id", 0)
            req_level = data.get("required_level", 0)
            item_class = data.get("item_class", {}).get("name", "Unknown Class")
            item_subclass = data.get("item_subclass", {}).get("name", "Unknown Subclass")
            purchase_price = format_with_gold(data.get("purchase_price", 0))
            wowhead_url = get_wowhead_item_link(id)

            return {
                "name": name,
                "level": level,
                "id": id,
                "req_level": req_level,
                "item_class": item_class,
                "item_subclass": item_subclass,
                "purchase_price": purchase_price,
                "wowhead_url": wowhead_url,
            }

            # return(
            #     f"Item Name: {name} (ID: {id}) | "
            #     f"Level: {level} | Req. Level: {req_level} | "
            #     f"Type: {item_class} ({item_subclass}) | "
            #     f"Vendor: {purchase_price}"
            # )


    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": "Error: Item not found."}
        return {"error": f"HTTP Error fetching character: {e.code}"}


def search_items(access_token: str, item_name: str, max_results: int = 5,
        region="us", locale="en_US") -> dict:
    
    query = urllib.parse.quote(item_name)
    namespace = f"static-{VERSION}-{region}"
    
    url = f"https://{region}.api.blizzard.com/data/wow/search/item?namespace={namespace}&name.en_US={query}&orderby=id&_page=1&locale={locale}" 
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")

    search_terms = item_name.lower().split()
    items_found = []

    try:
        with urllib.request.urlopen(req) as response:
            json_data = json.loads(response.read().decode())

            results = json_data.get("results", [])
            if not results:
                return {"error": "No items found."}

            for item in results:
                data = item.get("data", {})
                item_id = data.get("id")
                title = data.get("name", {}).get(locale, "Unknown Item")

                # Added client-side AND filter just like search_creatures
                if item_id and all(term in title.lower() for term in search_terms):
                    items_found.append({"id": item_id, "name": title})

                if len(items_found) >= max_results:
                    break
                
            if not items_found:
                return {"error": f"No items found for '{item_name}'."}

            return {
                "query": item_name,
                "results": items_found
            }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": "Error: Item search endpoint not found."}
        return {"error": f"HTTP Error fetching items: {e.code}"}
    except Exception as e:
        return {"error": str(e)}


def get_chararacter_base_stats(
        access_token: str,
        first_name: str,
        last_name: str,
        effective=True,
        region="us",
        locale="en_US"
        ) -> dict:

    
    
    
    character_slug = format_slug(f"{first_name}-{last_name}")
    category = "effective" if effective else "base"

    
    namespace = f"profile-{VERSION}-{region}"

    url = f"https://{region}.api.blizzard.com/profile/wow/character/{character_slug}/statistics?namespace={namespace}&locale={locale}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")

    try:
        with urllib.request.urlopen(req) as response:
            response: HTTPResponse = response
            data: dict[str, Any] = json.loads(response.read().decode())

            name = character_slug
            strength = data.get("strength", {}).get(category, 0)
            agility = data.get("agility", {}).get(category, 0)
            stamina = data.get("stamina", {}).get(category, 0)
            intellect = data.get("intellect", {}).get(category, 0)
            spirit = data.get("spirit", {}).get(category, 0)
            armor = data.get("armor", {}).get(category, 0)

            return {
                "name": f"{first_name.capitalize()} {last_name.capitalize()}",
                "strength": strength,
                "agility": agility,
                "stamina": stamina,
                "intellect": intellect,
                "spirit": spirit,
                "armor": armor,
                "effective": effective
            }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": "Error: Character statistics not found."}
        return {"error": "HTTP Error fetching character statistics."}
    except Exception as e:
        return {"error": str(e)}



def get_forever_realm_status(access_token: str, region: str = "us", locale: str = "en_US") -> dict:
    namespace = f"dynamic-forever-{region}"
    headers = {"Authorization": f"Bearer {access_token}"}
    ruleset_ids = [1, 2, 3, 15]
    statuses = []

    try:
        for rid in ruleset_ids:
            url = f"https://{region}.api.blizzard.com/data/wow/ruleset/{rid}?namespace={namespace}&locale={locale}"
            req = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                statuses.append({
                    "id": data.get("id"),
                    "name": data.get("name"),
                    "status": data.get("status", {}).get("name", "Unknown")
                })

        # Format into a single compact line for IRC
        # e.g., "PvP: Up | Normal: Up | Roleplay: Up | Roleplay PvP: Up"
        summary_str = " | ".join([f"{s['name']}: {s['status']}" for s in statuses])

        return {
            "version": "Forever",
            "rulesets": statuses,
            "irc_summary": summary_str
        }

    except urllib.error.HTTPError as e:
        return {"error": f"HTTP Error {e.code}"}
    except Exception as e:
        return {"error": str(e)}

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
        
        putlog(f"[{VERSION.upper()}] Gear Lookup <{nick}> {chan} - {first_name} {last_name}")

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

        putmsg(chan, f"[{VERSION.upper()}] {format_character_info_irc(character_info)}")

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching player character data.")


def pub_search_creatures(nick: str, user: str, hand: str, chan: str, text: str,
                       **kwargs):
    try:
        creature_name = format_slug(text)
        
        if not creature_name:
            putmsg(chan, "Usage: !csearch <creature name>")
            return
        
        

        putlog(f"Creature Search: <{nick}> on {chan} - {creature_name} [{VERSION.upper()}]")

        token = get_valid_blizzard_token()
        results = search_creatures(token, creature_name)

        putmsg(chan, format_creature_search_irc(results))

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching creature data.")


def pub_get_creature_summary(nick: str, user: str, hand: str, chan: str, text: str,
                          **kwargs):
    try:
        args = text.strip()
        if not args:
                putmsg(chan, "Usage !creature <creature_id>")
                return
        id = args


        putlog(f"Creature Summary: <{nick}> on {chan} - {id} [{VERSION.upper()}]")

        token = get_valid_blizzard_token()
        summary = get_creature_data(token, id)

        putmsg(chan, format_creature_summary(summary))

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching creature data.")


def pub_get_item_summary(nick: str, user: str, hand: str, chan: str, text: str,
                **kwargs):
    try:
        args = text.strip()
        if not args:
            putmsg(chan, "Usage: !item <item id>")
            return

        
        item_id = args

        if not item_id.isdigit():
            putmsg(chan, "Item ID must be numeric. Use !search to find the item ID.")
            return


        putlog(f"Item Lookup <{nick}> on {chan} -  {item_id} [{VERSION.upper()}]")
        
        token = get_valid_blizzard_token()
        item_data = get_item_data(token, item_id)
        


        putmsg(chan, format_item_data_irc(item_data))

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching WoW item data.")


def pub_search_items(nick: str, user: str, hand: str, chan: str, text:str,
                   **kwargs):
    try:
        query = text.strip()
        
        if not query:
            putmsg(chan, "Usage: !search <item name>")
            return        

        putlog(f"Item search: <{nick}> {chan} - {query} [{VERSION.upper()}]")

        token = get_valid_blizzard_token()
        results = search_items(token, query)

        putmsg(chan, format_item_search_irc(results))

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching WoW item data.")


def pub_get_character_bstats(nick: str, user: str, hand: str, chan: str, text: str,
                      **kwargs):
    try:
        args = text.strip()
        if not args:
            putmsg(chan, "Usage !stats <first_name> <last_name>")
            return

        args_split = args.split()
        arg_count = len(args_split)
        if arg_count != 2:
            putmsg(chan, "Usage !stats <first_name> <last_name>")
            return
        first_name, last_name = args_split

        token = get_valid_blizzard_token()

        putlog(f"Fetch Player Stats - <{nick}> on {chan} - {first_name.capitalize()} {last_name.capitalize()} [{VERSION.upper()}]")

        stats = get_chararacter_base_stats(token, first_name, last_name, False)
        putmsg(chan, format_base_stats_irc(stats))

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching player statistics.")


def pub_get_character_estats(nick: str, user: str, hand: str, chan: str, text: str,
                      **kwargs):
    try:
        args = text.strip()
        if not args:
            putmsg(chan, "Usage !stats <first_name> <last_name>")
            return

        args_split = args.split()
        arg_count = len(args_split)
        if arg_count != 2:
            putmsg(chan, "Usage !stats <first_name> <last_name>")
            return
        else:
            first_name, last_name = args_split

        token = get_valid_blizzard_token()

        putlog(f"Fetch Player Stats - <{nick}> on {chan} - {first_name.capitalize()} {last_name.capitalize()} [{VERSION.upper()}]")

        stats = get_chararacter_base_stats(token, first_name, last_name)
        putmsg(chan, format_base_stats_irc(stats))
    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching player statistics.")


def pub_compare_players(nick: str, user: str, handle: str, chan: str, text: str,
                      **kwargs):
    try:
        args = text.strip()
        if not args:
            putmsg(chan, "Usage !compare <first_name1> <last_name1> <first_name2> <last_name2>")
            return

        args_split = args.split()
        arg_count = len(args_split)
        if arg_count != 4:
            putmsg(chan, "Usage !compare <first_name1> <last_name1> <first_name2> <last_name2>")
            return
        first_name1, last_name1, first_name2, last_name2 = args_split

        token = get_valid_blizzard_token()
        name1 = f"{first_name1.capitalize()} {last_name1.capitalize()}"
        name2 = f"{first_name2.capitalize()} {last_name2.capitalize()}"

        putlog(f"Player Comparison - <{nick}> on {chan} - Comparing {name1} and {name2}")

        player1_data = get_character_data(token, first_name1, last_name1)
        player2_data = get_character_data(token, first_name2, last_name2)

        #test print data player 1
        putmsg(chan, format_player_compare_irc(player1_data, player2_data))

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching player data.")


def pub_get_forever_realm_status(nick: str, user: str, handle: str, chan: str, text: str,
                                 **kwargs):
    try:
        args_split = text.strip().split()
        if len(args_split) > 1:
            putmsg(chan, "Usage: !forever [region] (e.g., !forever or !forever eu)")
            return

        region = args_split[0].lower() if args_split else "us"

        putlog(f"WoW Forever Status Query - <{nick}> on {chan} - region: {region}")

        token = get_valid_blizzard_token()
        info = get_forever_realm_status(token, region=region)

        if "error" in info:
            putmsg(chan, f"Error: {info['error']}")
            return

        putmsg(chan, f"[{info['version']} - {region.upper()}] {info['irc_summary']}")

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching WoW Forever status.")
"""
***----------------------------------------------------------------------------
*** DCC BIND FUNCTIONS
***>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
"""

def dcc_token_debug(handle: str, idx: str, text: str,
                  **kwargs):
    try:
        putdcc(idx, f"Token: {get_valid_blizzard_token()}")

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putdcc(idx, "An error has occurred.")

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

def format_creature_search_irc(data: dict) ->str:
    if not data or "error" in data:
        return f"Error: {data.get('error', 'Search failed.')}"

    results = data.get("results", [])
    if not results:
        return f"No items found for '{data.get('query', '')}"

    formatted_items = [f"[{item['id']}] {item['name']}" for item in results]
    return " | ".join(formatted_items)


def format_creature_summary(data: dict) -> str:
    if not data or "error" in data:
        return f"Error: {data.get('error', 'Lookup failed.')}"

    return(
        f"Name: {data.get("name")} | Type: {data.get("type")} | Family: {data.get("family")} | Tameable: {data.get("tameable")} | "
        f"{data.get("wowhead_url")}"
    )

def format_item_data_irc(info: dict):
    if not info or "error" in info:
        return "Error: Invalid item data."
    return (
        f"Item Name: {info.get("name")} (ID: {info.get("id")}) | "
        f"Level: {info.get("level")} | Req. Level: {info.get("req_level")} | "
        f"{info.get("wowhead_url")}"

    )

def format_item_search_irc(data: dict) -> str:
    if not data or "error" in data:
        return f"Error: {data.get('error', 'Search failed.')}"

    results = data.get("results", [])
    if not results:
        return f"No items found for '{data.get('query', '')}"

    formatted_items = [f"[{item['id']}] {item['name']}" for item in results]
    return " | ".join(formatted_items)


def format_base_stats_irc(data: dict) -> str:

    if not data or "error" in data:
        return "Error: Invalid data."

    prefix = "" if data.get("effective") else " Base"
    return f"[{VERSION.upper()}] - {data['name']}{prefix} Stats: Str: {data['strength']} | Agi: {data['agility']} | Sta: {data['stamina']} | Int: {data['intellect']} | Spt: {data['spirit']} | Arm: {data['armor']}"


def format_player_compare_summary(player: dict):
    if not player or "error" in player:
        return "Error: Invalid player data"

    name = player.get("name")
    gender = player.get("gender")
    level = player.get("level")
    race = player.get("race")
    cls = player.get("class")
    ilvl = player.get("ilvl")
    xp_pct = player.get("xp_progress_pct")

    return f"{name} (Lvl {level} ({xp_pct}%) {race} {cls} | {ilvl} iLvl) ({gender})"


def format_player_compare_irc(player1: dict, player2: dict) -> str:
    if not player1 or not player2:
        return "Error: Internal error. Invalid player data."
    if "error" in player1:
        return f"{player1.get('error', 'Error: MissingNo')}"
    elif "error" in player2:
        return f"{player2.get('error', 'Error: MissingNo2')}"

    p1_summary = format_player_compare_summary(player1)
    p2_summary = format_player_compare_summary(player2)

    lvl1 = int(player1.get("level") or 0)
    lvl2 = int(player2.get("level") or 0)
    diff_level = lvl1 - lvl2

    ilvl1 = int(player1.get("ilvl") or 0)
    ilvl2 = int(player2.get("ilvl") or 0)
    diff_ilvl = ilvl1 - ilvl2
    
    name1 = player1.get("name", "Player 1")
    name2 = player2.get("name", "Player 2")
    
    return f"[{VERSION.upper()}] {p1_summary} vs {p2_summary} | Delta ({name1} vs {name2}): {diff_level:+d} Lvl, {diff_ilvl:+d} iLvl"


"""
***----------------------------------------------------------------------------
*** Bot Function Bindings Machine
***>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
"""

if 'WOW_BINDS' in globals(): 
    for wbind in WOW_BINDS:
        wbind.unbind()
    del WOW_BINDS


WOW_BINDS = list()

# Public commands
WOW_BINDS.append(bind("pub", "-", "!character", pub_get_character_summary))
WOW_BINDS.append(bind("pub", "-", "!gear", pub_get_character_gear))
WOW_BINDS.append(bind("pub", "-", "!csearch", pub_search_creatures))
WOW_BINDS.append(bind("pub", "-", "!creature", pub_get_creature_summary))
WOW_BINDS.append(bind("pub", "-", "!item", pub_get_item_summary))
WOW_BINDS.append(bind("pub", "-", "!search", pub_search_items))
WOW_BINDS.append(bind("pub", "-", "!bstats", pub_get_character_bstats))
WOW_BINDS.append(bind("pub", "-", "!stats", pub_get_character_estats))
WOW_BINDS.append(bind("pub", "-", "!compare", pub_compare_players))
WOW_BINDS.append(bind("pub", "-", "!status", pub_get_forever_realm_status))

WOW_BINDS.append(bind("dcc", "-", "token", dcc_token_debug))


# Dcc commands
#WOW_BINDS.append(bind("dcc", "-", "item", dcc_get_item_info))


putlog("Loaded forever.py!")
