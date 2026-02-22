import asyncio
import subprocess
import time

import httpx
from livekit import rtc
from nio import AsyncClient, MatrixRoom, RoomMessageText

from environment import MATRIX_HOMESERVER, MATRIX_PASSWORD, MATRIX_USER_ID

SAMPLE_RATE = 48000
NUM_CHANNELS = 1
SAMPLES_PER_CHANNEL = 480
BYTES_PER_FRAME = SAMPLES_PER_CHANNEL * 2

device_id = "riffkit-bot"

# track current processes so we can stop them
current_ydl_proc: subprocess.Popen | None = None
current_stream: subprocess.Popen | None = None


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


async def stream_audio(
    source: rtc.AudioSource, url: str, matrix_room_id: str, matrix: AsyncClient
):
    global current_stream, current_ydl_proc
    proc = None
    ydl_proc = None

    if current_stream:
        current_stream.kill()
        current_stream = None
    if current_ydl_proc:
        current_ydl_proc.kill()
        current_ydl_proc = None

    try:
        print(f"Starting stream for {url}...")

        # pipe yt-dlp directly into ffmpeg to avoid expiring URLs
        ydl_proc = subprocess.Popen(
            ["yt-dlp", "-f", "bestaudio", "-o", "-", "--quiet", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        current_ydl_proc = ydl_proc

        proc = subprocess.Popen(
            [
                "ffmpeg",
                "-i",
                "pipe:0",
                "-f",
                "s16le",
                "-ar",
                str(SAMPLE_RATE),
                "-ac",
                str(NUM_CHANNELS),
                "-loglevel",
                "error",
                "-",
            ],
            stdin=ydl_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        current_stream = proc

        loop = asyncio.get_event_loop()
        while True:
            data = await loop.run_in_executor(None, proc.stdout.read, BYTES_PER_FRAME)
            if not data or proc != current_stream:
                stderr_output = await loop.run_in_executor(None, proc.stderr.read)
                if stderr_output:
                    print(f"ffmpeg error: {stderr_output.decode()}")
                break

            frame = rtc.AudioFrame(
                data=data,
                sample_rate=SAMPLE_RATE,
                num_channels=NUM_CHANNELS,
                samples_per_channel=len(data) // 2,
            )
            await source.capture_frame(frame)

        await matrix.room_send(
            matrix_room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": "⏹️ Stream ended."},
        )

    except Exception as e:
        print(f"Streaming error: {e}")
        await matrix.room_send(
            matrix_room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": f"❌ Error: {e}"},
        )
    finally:
        if proc and current_stream == proc:
            proc.kill()
            current_stream = None
        if ydl_proc and current_ydl_proc == ydl_proc:
            ydl_proc.kill()
            current_ydl_proc = None


async def main():
    start_time = int(time.time() * 1000)  # ignore messages before this

    matrix = AsyncClient(MATRIX_HOMESERVER, MATRIX_USER_ID)
    await matrix.login(MATRIX_PASSWORD)
    print(f"Logged into Matrix as {MATRIX_USER_ID}")

    try:
        lk_url, lk_jwt = await get_livekit_credentials(
            matrix, "!MuZpVyeQhshKFklekb:matrix.org"
        )
        print(f"Connecting to LiveKit at {lk_url}...")

        lk_room = rtc.Room()
        await lk_room.connect(lk_url, lk_jwt)
        print(f"Connected to LiveKit room: {lk_room.name}")

        await matrix.room_put_state(
            room_id="!MuZpVyeQhshKFklekb:matrix.org",
            event_type="org.matrix.msc3401.call.member",
            state_key=f"_{MATRIX_USER_ID}_{device_id}_m.call",
            content={
                "application": "m.call",
                "call_id": "",
                "device_id": device_id,
                "expires": 3600000,
                "foci_preferred": [
                    {
                        "livekit_alias": "!MuZpVyeQhshKFklekb:matrix.org",
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
            global current_stream, current_ydl_proc

            if event.sender == MATRIX_USER_ID:
                return
            if event.server_timestamp < start_time:  # ignore old messages
                return
            if event.body.startswith("!play "):
                url = event.body[6:].strip()
                print(f"Playing: {url}")
                await matrix.room_send(
                    room.room_id,
                    message_type="m.room.message",
                    content={"msgtype": "m.text", "body": f"🎵 Loading: {url}"},
                )
                asyncio.create_task(stream_audio(source, url, room.room_id, matrix))
            elif event.body.strip() == "!stop":
                if current_stream:
                    current_stream.kill()
                    current_stream = None
                    if current_ydl_proc:
                        current_ydl_proc.kill()
                        current_ydl_proc = None
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

        matrix.add_event_callback(on_message, RoomMessageText)

        print("Listening for !play commands...")
        await matrix.sync(timeout=0, full_state=True)
        await matrix.sync_forever(timeout=30000)

    finally:
        await matrix.room_put_state(
            room_id="!MuZpVyeQhshKFklekb:matrix.org",
            event_type="org.matrix.msc3401.call.member",
            state_key=f"_{MATRIX_USER_ID}_{device_id}_m.call",
            content={},
        )
        await matrix.close()
        print("Cleaned up and exited")


if __name__ == "__main__":
    asyncio.run(main())
