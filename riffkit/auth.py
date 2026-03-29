import httpx
from nio import AsyncClient  # type: ignore

from riffkit.constants import device_id
from riffkit.environment import (
    MATRIX_HOMESERVER,
    MATRIX_USER_ID,
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
)


async def get_livekit_credentials(matrix: AsyncClient, room_id: str) -> tuple[str, str]:
    """Returns (livekit_url, jwt) for the given Matrix room."""

    async with httpx.AsyncClient(timeout=30.0) as http:
        resp = await http.post(
            f"{MATRIX_HOMESERVER}/_matrix/client/v3/user/{MATRIX_USER_ID}/openid/request_token",
            json={},
            headers={"Authorization": f"Bearer {matrix.access_token}"},
        )
        openid_token = resp.json()

        livekit_resp = await http.post(
            "https://livekit-jwt.call.matrix.org/sfu/get",
            json={
                "room": room_id,
                "openid_token": openid_token,
                "device_id": device_id,
            },
        )
        data = livekit_resp.json()
        return data["url"], data["jwt"]


async def get_spotify_token() -> str:
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        )
        return resp.json()["access_token"]
