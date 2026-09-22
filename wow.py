from http.client import HTTPResponse
import json
import base64
from pathlib import Path
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


def get_item_data(access_token: str, version: str, item_id, region="us", locale="en_US") -> dict :
    version = format_slug(version)
    version_slug = version_to_slug(version)
    namespace = f"static-{version_slug}-{region}"
    if version_slug == "invalid":
        return f"Error: Invalid game version. Must be 'era', 'tbc', or 'mop'"
    
    url = f"https://{region}.api.blizzard.com/data/wow/item/{item_id}?namespace={namespace}&locale={locale}"

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")

    try:
        with urllib.request.urlopen(req) as response:
            resp: HTTPResponse = response
            data: dict[str, any] = json.loads(resp.read().decode())

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
            return "Error: Item not found."
        return f"HTTP Error fetching character: {e.code}"

def format_item_data_irc(info: dict[str]):
    return (
        f"Item Name: {info.get("name")} (ID: {info.get("id")}) | "
        f"Level: {info.get("level")} | Req. Level: {req_level} | "

    )

def search_items_name(access_token: str, version: str, item_name, max_results = 5, region="us") -> str:
    query = urllib.parse.quote(item_name)
    version = format_slug(version)
    version_slug = version_to_slug(version)
    if version_slug == "invalid":
        return f"Error: Invalid game version. Must be 'era', 'tbc', or 'mop'"
    

    url = f"https://{region}.api.blizzard.com/data/wow/search/item?namespace=static-{version_slug}-{region}&name.en_US={query}&orderby=id&_page=1" 
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")

    result_return = list()
    search_terms = item_name.lower().split()

    try:

        with urllib.request.urlopen(req) as response:
            json_data = json.loads(response.read().decode())

            results = json_data.get("results", [])
            if not results:
                return "No items found."

            for item in results:
                data = item.get("data", {})
                item_id = data.get("id")
                title = data.get("name", {}).get("en_US", "Unknown Item")

                # Client side AND filter
                if item_id and all(term in title.lower() for term in search_terms):
                    result_return.append(f"[{item_id}] {title}")

                # Stop when we collect enough results
                if len(result_return) >= max_results:
                    break
                

            return " | ".join(result_return)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "Error: Item not found."
        return f"HTTP Error fetching character: {e.code}"


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
        

        putlog(f"Item search for: {search_query}")

        token = get_valid_blizzard_token()
        results = search_items_name(token, version, search_query)

        putmsg(chan, results)

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching WoW item data.")

def search_player_info(access_token: str, version: str, realm: str, character: str, region="us") -> dict :
    realm_slug = format_slug(realm)
    version = format_slug(version)
    version_slug = version_to_slug(version)
    if version_slug == "invalid":
        return "Error: Invalid game version. Must be 'era', 'tbc', or 'mop'"
    
    char_name = format_slug(character)

    url = f"https://{region}.api.blizzard.com/profile/wow/character/{realm_slug}/{char_name}?namespace=profile-{version_slug}-{region}&locale=en_US"
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

            # Guild is omitted from JSOn if player is unguilded
            guild_info = ""
            if "guild" in data:
                guild_name = data["guild"].get("name")
                if guild_name:
                    guild_info = f" | Guild: <{guild_name}>"

            return {
                "name": data.get("name", character.capitalize()),
                "level": data.get("level", 0),
                "race": data.get("race", {}).get("name", "Unknown Race"),
                "class": data.get("character_class", {}).get("name", "Unknown Class"),
                "realm_name": data.get("realm", {}).get("name", realm_slug.capitalize()),
                "faction": data.get("faction", {}).get("name", "Unknown Faction"),
                "ilvl": data.get("equipped_item_level"),
                "guild": guild_info
            }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return f"Character '{character}' on realm '{realm}' nout found."
        return f"HTTP Error fetching character: {e.code}"
            #return f"{name} - Lvl {level} {race} {cls} ({realm_name}) | Faction: {faction} | iLvl: {ilvl}{guild_info}"

def format_character_info_irc(info: dict) -> str:
    return f"{info['name']} - Lvl {info['level']} {info['race']} {info['class']} | Faction: {info['faction']} | iLvl: {info['ilvl']}{info['guild']}"

    # except urllib.error.HTTPError as e:
    #     if e.code == 404:
    #         return f"Character '{character}' on realm '{realm}' nout found."
    #     return f"HTTP Error fetching character: {e.code}"

def get_character_equipment(access_token: str, version:str, realm: str, character: str, region="us") -> list[str]:
    realm_slug = format_slug(realm)
    version = format_slug(version)
    version_slug = version_to_slug(version)
    if version_slug == "invalid":
        return [f"Error: Invalid game version. Must be 'era', 'tbc', or 'mop'"]
    

    character_name = character.lower()
    url = f"https://{region}.api.blizzard.com/profile/wow/character/{realm_slug}/{character_name}/equipment?namespace=profile-{version_slug}-{region}&locale=en_US"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")


    try:

        with urllib.request.urlopen(req) as response:
            response: HTTPResponse = response
            data = json.loads(response.read().decode())
            equip_data = data.get("equipped_items", {})

            if not equip_data:
                return ["No equipment data found."]

            items = []
            for piece in equip_data:
                name = piece.get("name", "Unknown Item")
                slot_name = piece.get("slot", {}).get("name", "Slot")
                items.append(f"{slot_name}: {name}")

            # Pack items into lines under 350 characters
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

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return [f"Character '{character}' on realm '{realm}' not found."]
        return [f"HTTP Error fetching character: {e.code}"]


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
        putlog(f"Gear Lookup for {name} on {realm}")

        token = get_valid_blizzard_token()
        equipment = get_character_equipment(token, version, realm, name)


        for line in equipment:
            putmsg(chan, line)

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching WoW item data")

def pubGetPlayerInfo(nick: str, user: str, hand: str, chan: str, text: str,
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

        
        putlog(f"Character lookup <{nick}> on {chan} - {name} on {realm}")

        token = get_valid_blizzard_token()
        character_info = search_player_info(token, version, realm, name)

        putmsg(chan, format_character_info_irc(character_info))

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


        putlog(f"Item Lookup for itemID: {query}")
        
        token = get_valid_blizzard_token()
        item_data = get_item_data(token, version, int(item_id))
        


        putmsg(chan, item_data)

    except Exception as e:
        putlog(f"wow.py Script Error:{e}")
        putlog(traceback.format_exc())
        putmsg(chan, "An error occurred fetching WoW item data.")


if 'WOW_BINDS' in globals():
    for wbind in WOW_BINDS:
        wbind.unbind()
    del WOW_BINDS

WOW_BINDS = list()
WOW_BINDS.append(bind("pub", "##wowclassic *", "!item", pubGetItemInfo))
WOW_BINDS.append(bind("pub", "##wowclassic *", "!search", pubSearchItems))
WOW_BINDS.append(bind("pub", "##wowclassic *", "!character", pubGetPlayerInfo))
WOW_BINDS.append(bind("pub", "##wowclassic *", "!gear", pubGetPlayerGear))
WOW_BINDS.append(bind("pub", "##wowclassic *", "!status", pubGetRealmStatus))

#bind("pub", "*", "!movie", pubGetMovie)

putlog("Loaded wow.py!")