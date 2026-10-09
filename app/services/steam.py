"""Steam Web API (owned games) and Steam OpenID 2.0 sign-in (proves account ownership)."""

import re
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import settings

API_URL = "https://api.steampowered.com"
OPENID_URL = "https://steamcommunity.com/openid/login"
ASSET_URL = "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps"

_OPENID_NS = "http://specs.openid.net/auth/2.0"
_IDENTIFIER_SELECT = "http://specs.openid.net/auth/2.0/identifier_select"
_CLAIMED_ID_RE = re.compile(r"^https?://steamcommunity\.com/openid/id/(\d{17})$")


class SteamError(Exception):
    pass


@dataclass
class OwnedGame:
    appid: int
    name: str
    playtime_minutes: int
    playtime_2weeks: int = 0  # minutes in the last two weeks (Steam omits it when 0)

    @property
    def cover_url(self) -> str:
        return f"{ASSET_URL}/{self.appid}/library_600x900.jpg"  # portrait 2:3, matches our cards


def profile_url(steam_id: str) -> str:
    return f"https://steamcommunity.com/profiles/{steam_id}"


async def get_owned_games(steam_id: str) -> list[OwnedGame] | None:
    """Return the user's games, or None if their game details are private."""
    if not settings.steam_api_key:
        raise SteamError("STEAM_API_KEY is not set")
    params = {
        "key": settings.steam_api_key,
        "steamid": steam_id,
        "include_appinfo": 1,
        "include_played_free_games": 1,
        "format": "json",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{API_URL}/IPlayerService/GetOwnedGames/v1/", params=params)
        r.raise_for_status()
        data = r.json().get("response", {})
    except (httpx.HTTPError, ValueError) as e:
        raise SteamError(str(e)) from e

    if "games" not in data:
        # Steam returns an empty response for private libraries, game_count 0 for public empty ones.
        return [] if data.get("game_count") == 0 else None
    return [
        OwnedGame(
            appid=g["appid"],
            name=g.get("name") or f"App {g['appid']}",
            playtime_minutes=g.get("playtime_forever", 0),
            playtime_2weeks=g.get("playtime_2weeks", 0),
        )
        for g in data["games"]
    ]


def openid_login_url(return_to: str, realm: str) -> str:
    params = {
        "openid.ns": _OPENID_NS,
        "openid.mode": "checkid_setup",
        "openid.return_to": return_to,
        "openid.realm": realm,
        "openid.identity": _IDENTIFIER_SELECT,
        "openid.claimed_id": _IDENTIFIER_SELECT,
    }
    return f"{OPENID_URL}?{urlencode(params)}"


async def verify_openid(params: dict[str, str]) -> str | None:
    """Ask Steam to confirm the signed callback params; return the SteamID64 if valid."""
    if params.get("openid.mode") != "id_res" or params.get("openid.op_endpoint") != OPENID_URL:
        return None
    match = _CLAIMED_ID_RE.match(params.get("openid.claimed_id", ""))
    if match is None:
        return None
    check = {k: v for k, v in params.items() if k.startswith("openid.")}
    check["openid.mode"] = "check_authentication"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(OPENID_URL, data=check)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise SteamError(str(e)) from e
    return match.group(1) if "is_valid:true" in r.text else None


async def get_app_details(appid: str) -> dict | None:
    """Store-page data (description, genres, developers) in Traditional Chinese, or None."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://store.steampowered.com/api/appdetails",
                params={"appids": appid, "l": "tchinese", "cc": "tw"},
            )
        entry = (r.json() or {}).get(str(appid)) or {}
    except (httpx.HTTPError, ValueError):
        return None
    return entry.get("data") if entry.get("success") else None
