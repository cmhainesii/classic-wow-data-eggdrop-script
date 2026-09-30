from http.client import HTTPResponse
import json
import base64
from pathlib import Path
from typing import Any
import urllib.error
import urllib.parse
import urllib.request
import traceback
import time
import os
from dotenv import load_dotenv

from eggdrop import bind
from eggdrop.tcl import putmsg, putlog

# API Credentials
#CLIENT_ID = "6d90fc49d9bf4ddea058e3a428036577"
#CLIENT_SECRET = "tX7yyYMTut6BkYjkjL53eEwJaRaB21UN"

load_dotenv()
CLIENT_ID = os.getenv("BLIZZARD_CLIENT_ID")
CLIENT_SECRET = os.getenv("BLIZZARD_CLIENT_SECRET")

_TOKEN_CACHE = {"access_token": None, "expires_at": 0}


def format_with_gold(copper_in) -> str :
    gold = copper_in // 10_000
    silver = copper_in % 10_000 // 100
    copper = copper_in % 100
    return f"{gold}g {silver}s {copper}c"

def format_slug(realm: str) -> str:
    return realm.strip().lower().replace(' ', '-').replace("'", "")

def version_to_slug(version: str):
    if version == "era":
        return "classic1x"
    elif version == "tbc":
        return "classicann"
    elif version == "mop":
        return "classic"
    else:
        return "invalid"

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
    
def get_realm_status(
        access_token:str,
        version: str,
        realm: str,
        region: str = "us",
        locale: str = "en_US"
) -> dict:
    """
    Queries the Realm Index API directly to fetch all available realms for a given
    game version and region
    """
    realm_slug = format_slug(realm)
    version = format_slug(version)
    version_slug = version_to_slug(version)

    if version_slug == "invalid":
        return {"error": f"Invalid game version"}
    namespace = f"dynamic-{version_slug}-{region}"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        # Step 1:Fetch realm to get it's connected_realm URL/ID
        realm_url = f"https://{region}.api.blizzard.com/data/wow/realm/{realm_slug}?namespace={namespace}&locale={locale}"
        req = urllib.request.Request(realm_url, headers=headers)

        with urllib.request.urlopen(req) as response:
            response: HTTPResponse = response
            realm_data = json.loads(response.read().decode())
            connected_href = realm_data.get("connected_realm", {}).get("href")

            if not connected_href:
                return {"error": f"Cound not find connected realm for '{realm}'"}

            # Step 2: Fetch the connected realm directly for live state
            conn_url = f"{connected_href}&locale={locale}" if "?" in connected_href else f"{connected_href}?locale={locale}"
            req_conn = urllib.request.Request(conn_url, headers=headers)

            with urllib.request.urlopen(req_conn) as response:
                response: HTTPResponse = response
                status_data = json.loads(response.read().decode())

                return {
                    "realm": realm_data.get("name", realm_slug.capitalize()),
                    "status": status_data.get("status", {}).get("name", "Unknown"),
                    "population": status_data.get("population", {}).get("name", "Unknown"),
                    "has_queue": status_data.get("has_queue", False),
                    "connected_realm_id": status_data.get("id")
                }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": f"Realm '{realm_slug.capitalize()}' not found in namespace '{namespace}'."}
        return {"error": f"HTTP Error {e.code}"}
    except Exception as e:
        return {"error": str(e)}


# Gets characters effective stats
def get_chararacter_base_estats(
        access_token: str,
        version: str,
        realm: str,
        character: str,
        region="us",
        locale="en_US"
        ) -> dict:

    realm_slug = format_slug(realm)
    version_slug = format_slug(version)
    version_slug = version_to_slug(version_slug)
    character_slug = format_slug(character)

    if not version_slug or "invalid" in version_slug:
        return {"error": "Invalid game version. Must be 'era', 'tbc', or 'mop'."}
    
    namespace = f"profile-{version_slug}-{region}"

    url = f"https://{region}.api.blizzard.com/profile/wow/character/{realm_slug}/{character_slug}/statistics?namespace={namespace}&locale={locale}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")

    try:
        with urllib.request.urlopen(req) as response:
            response: HTTPResponse = response
            data: dict[str, Any] = json.loads(response.read().decode())

            name = character_slug.capitalize()
            realm_formatted = realm_slug.capitalize()
            version_formatted = format_slug(version).upper()
            strength = data.get("strength", {}).get("effective", 0)
            agility = data.get("agility", {}).get("effective", 0)
            stamina = data.get("stamina", {}).get("effective", 0)
            intellect = data.get("intellect", {}).get("effective", 0)
            spirit = data.get("spirit", {}).get("effective", 0)
            armor = data.get("armor", {}).get("effective", 0)

            return {
                "name": name,
                "realm": realm_formatted,
                "version": version_formatted,
                "strength": strength,
                "agility": agility,
                "stamina": stamina,
                "intellect": intellect,
                "spirit": spirit,
                "armor": armor
            }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": "Error: Character statistics not found."}
        return {"error": "HTTP Error fetching character statistics."}
    except Exception as e:
        return {"error": str(e)}


def format_base_stats_irc(data: dict) -> str:

    if not data or "error" in data:
        return "Error: Invalid data."

    return f"[{data['version']}] - {data['name']}-{data['realm']} Stats: Str: {data['strength']} | Agi: {data['agility']} | Sta: {data['stamina']} | Int: {data['intellect']} Spt: {data['spirit']} Arm: {data['armor']}"

    


    


def get_item_data(access_token: str, version: str, item_id, region="us", locale="en_US") -> dict :
    version = format_slug(version)
    version_slug = version_to_slug(version)
    namespace = f"static-{version_slug}-{region}"
    if version_slug == "invalid":
        return {"error": f"Error: Invalid game version. Must be 'era', 'tbc', or 'mop'"}
    
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

            return {
                "name": data.get("name", "Unknown Item"),
                "level": data.get("level", 0),
                "id": data.get(id, 0),
                "req_level": data.get("required_level", 0),
                "item_class": data.get("item_class", {}).get("name", "Unknown Class"),
                "item_subclass": data.get("item_subclass", {}).get("name", "Unknown Subclass"),
                "purchase_price": format_with_gold(data.get("purchase_price", 0))
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

def format_item_data_irc(info: dict):
    if not info or "error" in info:
        return "Error: Invalid item data."
    return (
        f"Item Name: {info.get("name")} (ID: {info.get("id")}) | "
        f"Level: {info.get("level")} | Req. Level: {info.get("req_level")} | "

    )

def search_items_name(
        access_token: str,
        version: str,
        item_name: str,
        max_results: int = 5,
        region="us",
        locale="en_US"
        ) -> dict:
    
    query = urllib.parse.quote(item_name)
    version = format_slug(version)
    version_slug = version_to_slug(version)
    namespace = f"static-{version_slug}-{region}"
    if version_slug == "invalid":
        return {"error": f"Error: Invalid game version. Must be 'era', 'tbc', or 'mop'"}
    

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
                title = data.get("name", {}).get("en_US", "Unknown Item")

                # Client side AND filter
                if item_id and all(term in title.lower() for term in search_terms):
                    items_found.append({"id": item_id, "name": title})

                # Stop when we collect enough results
                if len(items_found) >= max_results:
                    break
                

            #return " | ".join(result_return)
            return {
                "query": item_name,
                "results": items_found
            }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": "Error: Item search endpoint not found."}
        return {"error": f"HTTP Error fetching character: {e.code}"}
    except Exception as e:
        return {"error": str(e)}


def format_item_search_irc(data: dict) -> str:
    if not data or "error" in data:
        return f"Error: {data.get('error', 'Search failed.')}"

    results = data.get("results", [])
    if not results:
        return f"No items found for '{data.get('query', '')}"

    formatted_items = [f"[{item['id']}] {item['name']}" for item in results]
    return " | ".join(formatted_items)

def pubSearchItems(nick: str, user: str, hand: str, chan: str, text:str,
                   **kwargs):
    try:
        query = text.strip()
        if not query:
            putmsg(chan, "Usage !search <era/tbc/mop> <item name>")
            return

        if len(query.split()) < 2:
            putmsg(chan, "Usage !search <era/tbc/mop> <item name>")
            return

        version, search_query = query.split(maxsplit=1)
        

        putlog(f"Item search: <{nick}> {chan} - {search_query} [{version}]")

        token = get_valid_blizzard_token()
        results = search_items_name(token, version, search_query)

        putmsg(chan, format_item_search_irc(results))

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching WoW item data.")




        

def get_character_data(access_token: str, version: str, realm: str, character: str, region="us", locale="en_US") -> dict :
    realm_slug = format_slug(realm)
    version = format_slug(version)
    version_slug = version_to_slug(version)
    if version_slug == "invalid":
        return {"error": "Error: Invalid game version. Must be 'era', 'tbc', or 'mop'"}
    
    char_name = format_slug(character)
    namespace = f"profile-{version_slug}-{region}"

    url = f"https://{region}.api.blizzard.com/profile/wow/character/{realm_slug}/{char_name}?namespace={namespace}&locale={locale}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")

    try:
        with urllib.request.urlopen(req) as response:
            data =json.loads(response.read().decode())

            name = data.get("name", character.capitalize())
            level = data.get("level", 0)
            race = data.get("race", {}).get("name", "Unknown Race")
            cls = data.get("character_class", {}).get("name", "Unknown Class")
            realm_name = data.get("realm", {}).get("name", realm.capitalize())
            faction = data.get("faction", {}).get("name", "Unknown Faction")
            ilvl = data.get("equipped_item_level", 0)
            gender = data.get("gender", {}).get("name", "Unknown Gender")

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
                "realm_name": realm_name,
                "faction": faction,
                "ilvl": ilvl,
                "gender": gender,
                "guild": guild_info,
                "version": version
            }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": f"Character '{character}' on realm '{realm}' not found."}
        return {"error": f"HTTP Error fetching character: {e.code}"}

    # [TBC] Mogrimxii-Dreamscythe (Lvl 70 Night Elf Hunter | 115.4 iLvl) vs Norfair-Windseeker (Lvl 68 Undead Priest | 98.2 iLvl) | Delta: Mogrimxii +2 Lvl, +17.2 iLvl
      
    
def format_player_compare_summary(player: dict):
    if not player or "error" in player:
        return "Error: Invalid player data"

    
    name = player.get("name")
    gender = player.get("gender")
    realm = player.get("realm_name")
    level = player.get("level")
    race = player.get("race")
    cls = player.get("class")
    ilvl = player.get("ilvl")

    return f"{name}-{realm} (Lvl {level} {race} {cls} | {ilvl} iLvl) ({gender})"
    #return f"[{player.get("version", "WOW").capitalize()}] {player.get("name")}-{player.get("realm_name", "Unknown").capitalize()} (Lvl {player.get("level", 0)} {player.get("race")} {player.get("class")} | {player.get("ilvl", 0)} iLvl)"      


def format_player_compare_irc(player1: dict, player2: dict) -> str:
    if not player1 or "error" in player1:
        return "Error: Invalid player1 data."
    elif not player2 or "error" in player2:
        return "Error: Invalid player2 data."

    p1_summary = format_player_compare_summary(player1)
    p2_summary = format_player_compare_summary(player2)

    lvl1 = int(player1.get("level") or 0)
    lvl2 = int(player2.get("level") or 0)
    diff_level = lvl1 - lvl2

    ilvl1 = int(player1.get("ilvl") or 0)
    ilvl2 = int(player2.get("ilvl") or 0)
    diff_ilvl = ilvl1 - ilvl2
    
    version = player1.get("version", "")
    name = player1.get("name", "Unknown Name")
    return f"[{version.upper()}] {p1_summary} vs {p2_summary} | Delta: {name} {diff_level:+d} Lvl, {diff_ilvl:+d} iLvl" 


def format_character_info_irc(info: dict) -> str:
    if not info or "error" in info:
        return "Error: Invalid character data."

    return f"{info['name']} ({info['gender']})- Lvl {info['level']} {info['race']} {info['class']} | Faction: {info['faction']} | iLvl: {info['ilvl']}{info['guild']}"


def get_character_equipment(access_token: str, version: str, realm: str, character: str, region="us", locale="en_US") -> dict:
    realm_slug = format_slug(realm)
    version_slug = format_slug(version)
    version_slug = version_to_slug(version_slug)
    namespace = f"profile-{version_slug}-{region}"
    
    if "invalid" in version_slug:
        return {"error": "Invalid game version. Must be 'era', 'tbc', or 'mop'."}
    
    character_name = character.lower()
    url = f"https://{region}.api.blizzard.com/profile/wow/character/{realm_slug}/{character_name}/equipment?namespace={namespace}&locale={locale}"
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
                "character": character,
                "realm": realm,
                "version": version,
                "equipment": equipment
            }
        
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": f"Character '{character}' on realm '{realm}' not found."}
        return {"error": f"HTTP Error fetching character: {e.code}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}
    

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


        

    



    

# def get_character_equipment(access_token: str, version:str, realm: str, character: str, region="us", locale="en_US") -> list[str]:
#     realm_slug = format_slug(realm)
#     version = format_slug(version)
#     version_slug = version_to_slug(version)
#     if version_slug == "invalid":
#         return [f"Error: Invalid game version. Must be 'era', 'tbc', or 'mop'"]
    

#     character_name = character.lower()
    
#     req = urllib.request.Request(url)
#     req.add_header("Authorization", f"Bearer {access_token}")


#     try:

#         with urllib.request.urlopen(req) as response:
#             response: HTTPResponse = response
#             data = json.loads(response.read().decode())
#             equip_data = data.get("equipped_items", {})

#             if not equip_data:
#                 return ["No equipment data found."]

#             items = []
#             for piece in equip_data:
#                 name = piece.get("name", "Unknown Item")
#                 slot_name = piece.get("slot", {}).get("name", "Slot")
#                 items.append(f"{slot_name}: {name}")

#             # Pack items into lines under 350 characters
#             lines = []
#             current_line = []
#             current_len = 0
#             MAX_LEN = 350

#             for item in items:
#                 # 3 accounts for the " | " separator
#                 added_len = len(item) + (3 if current_line else 0)
#                 if current_len + added_len > MAX_LEN:
#                     lines.append(" | ".join(current_line))
#                     current_line = [item]
#                     current_len = len(item)
#                 else:
#                     current_line.append(item)
#                     current_len += added_len

#             if current_line:
#                 lines.append(" | ".join(current_line))

#             return lines

#     except urllib.error.HTTPError as e:
#         if e.code == 404:
#             return [f"Character '{character}' on realm '{realm}' not found."]
#         return [f"HTTP Error fetching character: {e.code}"]


def pubGetPlayerGear(nick: str, user: str, hand: str, chan: str, text: str,
                     **kwargs):
    try:
        query = text.strip()
        if not query:
            putmsg(chan, "Usage !gear <era/tbc/mop> <realm> <name>")
            return

        query = query.split()
        if len(query) < 3:
            putmsg(chan, "Usage !gear <era/tbc/mop> <realm> <name>")
            return

        version, realm, name = query[0], query[1], query[2]
        putlog(f"Gear Lookup <{nick}> {chan} - {name}-{realm}")

        token = get_valid_blizzard_token()
        equipment = get_character_equipment(token, version, realm, name)


        for line in format_character_equipment_irc(equipment):
            putmsg(chan, line)

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching WoW item data")

def pubCharacterInfo(nick: str, user: str, hand: str, chan: str, text: str,
                     **kwargs):
    try:
        query = text.strip()
        if not query:
            putmsg(chan, "Usage: !character <era/tbc/mop> <realm> <name>")
            return

        query = query.split()
        if len(query) < 3:
            putmsg(chan, "Usage: !character <era/tbc/mop> <realm> <name>")
            return
        version, realm, name = query[0], query[1], query[2]

        
        putlog(f"Character lookup <{nick}> on {chan} - {name}-{realm}")

        token = get_valid_blizzard_token()
        character_info = get_character_data(token, version, realm, name)

        putmsg(chan, f"[{version.upper()}] {format_character_info_irc(character_info)}")

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching WoW item data.")

def pubGetRealmStatus(nick: str, user: str, handle: str, chan: str, text: str,
                      **kwargs):
    try:
        args = text.strip()
        if not args:
            putmsg(chan, "Usage: !status <era/tbc/mop> <realm>")
            return

        args_split = args.split()
        if len(args_split) < 2:
            putmsg(chan, "Usage: !status <era/tbc/mop> <realm>")
            return

        version, realm = args_split


        putlog(f"Realm Status Query - <{nick}> on {chan} - {realm}")

        token = get_valid_blizzard_token()
        info = get_realm_status(token, version, realm)
        queue_str = "Yes" if info['has_queue'] else "No"
        putmsg(chan, f"[{info['realm']}] Status: {info['status']} | Pop: {info['population']} | Queue: {queue_str}")
 
    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching realm status.")


def pubComparePlayers(nick: str, user: str, handle: str, chan: str, text: str,
                      **kwargs):
    try:
        args = text.strip()
        if not args:
            putmsg(chan, "Usage !compare <era/tbc/mop> <realm> <player1> <player2>")
            return

        args_split = args.split()
        if len(args_split) < 4:
            putmsg(chan, "Usage !compare <era/tbc/mop> <realm> <player1> <player2>")
            return

        version, realm, player1, player2 = args_split
        token = get_valid_blizzard_token()
        

        putlog(f"Player Comparison - <{nick}> on {chan} - {player1} {player2} - {realm}")

        player1_data = get_character_data(token, version, realm, player1)
        player2_data = get_character_data(token, version, realm, player2)

        #test print data player 1
        putmsg(chan, format_player_compare_irc(player1_data, player2_data))

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching player data.")


def pubCharacterStats(nick: str, user: str, hand: str, chan: str, text: str,
                      **kwargs):
    try:
        args = text.strip()
        if not args:
            putmsg(chan, "Usage !stats <era/tbc/mop> <realm> <character>")
            return

        args_split = args.split()
        if len(args_split) < 3:
            putmsg(chan, "Usage !stats <era/tbc/mop> <realm> <character>")
            return

        version, realm, character = args_split
        token = get_valid_blizzard_token()

        putlog(f"Fetch Player Stats - <{nick}> on {chan} - {character} [{version}]")

        stats = get_chararacter_base_estats(token, version, realm, character)
        putmsg(chan, format_base_stats_irc(stats))
    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching player statistics.")

        


def pubGetItemInfo(nick: str, user: str, hand: str, chan: str, text: str,
                **kwargs):
    try:
        query = text.strip()
        if not query:
            putmsg(chan, "Usage: !item <era/tbc/mop> <item id>")
            return

        query = query.split()

        if len(query) < 2:
            putmsg(chan, "Usage: !item <era/tbc/mop> <item id>")
            return
        version, item_id = query[0], query[1]

        if not item_id.isdigit():
            putmsg(chan, "Item ID must be numeric. Use !search to find the item ID.")
            return


        putlog(f"Item Lookup <{nick}> on {chan} -  {item_id} [{version}]")
        
        token = get_valid_blizzard_token()
        item_data = get_item_data(token, version, int(item_id))
        


        putmsg(chan, format_item_data_irc(item_data))

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching WoW item data.")


if 'WOW_BINDS' in globals(): 
    for wbind in WOW_BINDS:
        wbind.unbind()
    del WOW_BINDS


TESTING_MASK = "##wowclassic *"

WOW_BINDS = list()
WOW_BINDS.append(bind("pub", TESTING_MASK, "!item", pubGetItemInfo))
WOW_BINDS.append(bind("pub", TESTING_MASK, "!search", pubSearchItems))
WOW_BINDS.append(bind("pub", TESTING_MASK, "!character", pubCharacterInfo))
WOW_BINDS.append(bind("pub", TESTING_MASK, "!gear", pubGetPlayerGear))
WOW_BINDS.append(bind("pub", TESTING_MASK, "!status", pubGetRealmStatus))
WOW_BINDS.append(bind("pub", TESTING_MASK, "!compare", pubComparePlayers))
WOW_BINDS.append(bind("pub", TESTING_MASK, "!stats", pubCharacterStats))

#bind("pub", "*", "!movie", pubGetMovie)

putlog("Loaded wow.py!")