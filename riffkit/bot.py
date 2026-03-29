import asyncio
import time

import httpx
from livekit import rtc
from nio import AsyncClient, MatrixRoom, RoomMessageText  # type: ignore

from riffkit.auth import get_livekit_credentials, get_spotify_token
from riffkit.constants import NUM_CHANNELS, SAMPLE_RATE, device_id
from riffkit.environment import (
    MATRIX_HOMESERVER,
    MATRIX_PASSWORD,
    MATRIX_ROOM_ID,
    MATRIX_USER_ID,
)
from riffkit.stream import is_playing, stop_stream, stream_audio

track_queue: list[str] = []
queue_task: asyncio.Task | None = None


async def expand_url(url: str) -> list[str]:
    """Return a list of individual track URLs, expanding playlists/albums."""
    if "open.spotify.com/playlist/" in url:
        playlist_id = url.split("/playlist/")[1].split("?")[0]
        token = await get_spotify_token()
        tracks = []
        async with httpx.AsyncClient() as http:
            offset = 0
            while True:
                resp = await http.get(
                    f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"limit": 100, "offset": offset},
                )
                data = resp.json()
                for item in data.get("items", []):
                    track = item.get("track")
                    if track:
                        tracks.append(track["external_urls"]["spotify"])
                if not data.get("next"):
                    break
                offset += 100
        return tracks

    elif "open.spotify.com/album/" in url:
        album_id = url.split("/album/")[1].split("?")[0]
        token = await get_spotify_token()
        tracks = []
        async with httpx.AsyncClient() as http:
            offset = 0
            while True:
                resp = await http.get(
                    f"https://api.spotify.com/v1/albums/{album_id}/tracks",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"limit": 50, "offset": offset},
                )
                data = resp.json()
                for track in data.get("items", []):
                    tracks.append(track["external_urls"]["spotify"])
                if not data.get("next"):
                    break
                offset += 50
        return tracks

    else:
        # Use yt-dlp to expand YouTube playlists; single URLs come back as-is
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--flat-playlist",
            "--print",
            "url",
            "--no-warnings",
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        urls = [u for u in stdout.decode().strip().split("\n") if u.startswith("http")]
        return urls if urls else [url]


async def run_queue(source: rtc.AudioSource, matrix_room_id: str, matrix: AsyncClient):
    global queue_task, track_queue
    try:
        while track_queue:
            url = track_queue.pop(0)
            await stream_audio(source, url, matrix_room_id, matrix)
        await matrix.room_send(
            matrix_room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": "⏹️ Queue finished."},
        )
    finally:
        queue_task = None


async def main():
    start_time = int(time.time() * 1000)

    matrix = AsyncClient(MATRIX_HOMESERVER, MATRIX_USER_ID)
    await matrix.login(MATRIX_PASSWORD)
    print(f"Logged into Matrix as {MATRIX_USER_ID}")

    try:
        lk_url, lk_jwt = await get_livekit_credentials(matrix, MATRIX_ROOM_ID)
        print(f"Connecting to LiveKit at {lk_url}...")

        lk_room = rtc.Room()
        await lk_room.connect(lk_url, lk_jwt)
        print(f"Connected to LiveKit room: {lk_room._info}")

        await matrix.room_put_state(
            room_id=MATRIX_ROOM_ID,
            event_type="org.matrix.msc3401.call.member",
            state_key=f"_{MATRIX_USER_ID}_{device_id}_m.call",
            content={
                "application": "m.call",
                "call_id": "",
                "device_id": device_id,
                "expires": int(time.time() * 1000) + 8 * 3600000,  # 8 hours from now
                "foci_preferred": [
                    {
                        "livekit_alias": MATRIX_ROOM_ID,
                        "livekit_service_url": "https://livekit-jwt.call.matrix.org",
                        "type": "livekit",
                    }
                ],
                "focus_active": {
                    "focus_selection": "oldest_membership",
                    "type": "livekit",
                },
                "m.call.intent": "video",
                "scope": "m.room",
            },
        )
        print("Announced as call participant")

        source = rtc.AudioSource(sample_rate=SAMPLE_RATE, num_channels=NUM_CHANNELS)
        track = rtc.LocalAudioTrack.create_audio_track("music", source)
        options = rtc.TrackPublishOptions(
            source=rtc.TrackSource.SOURCE_MICROPHONE,
            dtx=False,
        )
        await lk_room.local_participant.publish_track(track, options)

        async def on_message(room: MatrixRoom, event: RoomMessageText):
            global track_queue, queue_task

            if event.sender == MATRIX_USER_ID:
                return
            if event.server_timestamp < start_time:
                return

            if event.body.startswith("!play "):
                url = event.body[6:].strip()
                print(f"Expanding: {url}")
                await matrix.room_send(
                    room.room_id,
                    message_type="m.room.message",
                    content={"msgtype": "m.text", "body": f"🔍 Loading: {url}"},
                )

                urls = await expand_url(url)

                if queue_task and not queue_task.done():
                    queue_task.cancel()
                    try:
                        await queue_task
                    except asyncio.CancelledError:
                        pass
                stop_stream()

                track_queue = urls

                if len(urls) > 1:
                    await matrix.room_send(
                        room.room_id,
                        message_type="m.room.message",
                        content={
                            "msgtype": "m.text",
                            "body": f"🎵 Queued {len(urls)} tracks.",
                        },
                    )
                else:
                    await matrix.room_send(
                        room.room_id,
                        message_type="m.room.message",
                        content={"msgtype": "m.text", "body": f"🎵 Playing: {urls[0]}"},
                    )

                queue_task = asyncio.create_task(
                    run_queue(source, room.room_id, matrix)
                )

            elif event.body.strip() in ("!skip", "!next"):
                if track_queue or is_playing():
                    stop_stream()
                    remaining = len(track_queue)
                    msg = (
                        f"⏭️ Skipped. {remaining} track(s) remaining."
                        if remaining
                        else "⏭️ Skipped. Queue is empty."
                    )
                    await matrix.room_send(
                        room.room_id,
                        message_type="m.room.message",
                        content={"msgtype": "m.text", "body": msg},
                    )
                else:
                    await matrix.room_send(
                        room.room_id,
                        message_type="m.room.message",
                        content={"msgtype": "m.text", "body": "Nothing is playing."},
                    )

            elif event.body.strip() == "!stop":
                if queue_task and not queue_task.done():
                    queue_task.cancel()
                    try:
                        await queue_task
                    except asyncio.CancelledError:
                        pass
                track_queue = []
                if is_playing():
                    stop_stream()
                    await matrix.room_send(
                        room.room_id,
                        message_type="m.room.message",
                        content={"msgtype": "m.text", "body": "⏹️ Stopped."},
                    )
                else:
                    await matrix.room_send(
                        room.room_id,
                        message_type="m.room.message",
                        content={"msgtype": "m.text", "body": "Nothing is playing."},
                    )

            elif event.body.strip() == "!queue":
                if not track_queue and not is_playing():
                    body = "Queue is empty."
                else:
                    lines = ["Current queue:"]
                    if is_playing():
                        lines.append("▶️ (playing)")
                    for i, u in enumerate(track_queue, 1):
                        lines.append(f"{i}. {u}")
                    body = "\n".join(lines)
                await matrix.room_send(
                    room.room_id,
                    message_type="m.room.message",
                    content={"msgtype": "m.text", "body": body},
                )

        matrix.add_event_callback(on_message, RoomMessageText)

        print("Listening for commands...")
        await matrix.sync(timeout=0, full_state=True)
        await matrix.sync_forever(timeout=30000)

    finally:
        await matrix.room_put_state(
            room_id=MATRIX_ROOM_ID,
            event_type="org.matrix.msc3401.call.member",
            state_key=f"_{MATRIX_USER_ID}_{device_id}_m.call",
            content={},
        )
        await matrix.close()
        print("Cleaned up and exited")
