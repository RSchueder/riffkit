import asyncio

import httpx
from nio import AsyncClient

from environment import MATRIX_HOMESERVER, MATRIX_PASSWORD, MATRIX_USER_ID


async def main():
    matrix = AsyncClient(MATRIX_HOMESERVER, MATRIX_USER_ID)
    await matrix.login(MATRIX_PASSWORD)

    access_token = matrix.access_token

    async with httpx.AsyncClient() as http:
        # step 1: get openid token
        resp = await http.post(
            f"{MATRIX_HOMESERVER}/_matrix/client/v3/user/{MATRIX_USER_ID}/openid/request_token",
            json={},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        print("OpenID response:", resp.json())
        openid_token = resp.json()

        # step 2: exchange with livekit token service
        livekit_resp = await http.post(
            "https://livekit-jwt.call.matrix.org/sfu/get",
            json={
                "room": "!MuZpVyeQhshKFklekb:matrix.org",
                "openid_token": openid_token,
                "device_id": "riffkit-bot",
            },
        )
        print("LiveKit token response:", livekit_resp.status_code, livekit_resp.text)

    await matrix.close()


asyncio.run(main())
