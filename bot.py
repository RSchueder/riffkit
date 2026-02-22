import asyncio
import subprocess

import yt_dlp
from livekit import api, rtc
from nio import AsyncClient, MatrixRoom, RoomMessageText

from environment import (API_KEY, API_SECRET, LIVEKIT_URL, MATRIX_HOMESERVER,
                         MATRIX_PASSWORD, MATRIX_USER_ID)

SAMPLE_RATE = 48000
NUM_CHANNELS = 1
SAMPLES_PER_CHANNEL = 480
BYTES_PER_FRAME = SAMPLES_PER_CHANNEL * 2

# track current ffmpeg process so we can stop it
current_stream: subprocess.Popen | None = None


def resolve_stream_url(url: str) -> str:
    with yt_dlp.YoutubeDL({"format": "bestaudio", "quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        return info["url"]


async def stream_audio(source: rtc.AudioSource, url: str, matrix_room_id: str, matrix: AsyncClient):
    global current_stream

    if current_stream:
        current_stream.kill()
        current_stream = None

    try:
        print(f"Resolving stream URL for {url}...")
        stream_url = resolve_stream_url(url)

        proc = subprocess.Popen(
            [
                "ffmpeg", "-i", stream_url,
                "-f", "s16le",
                "-ar", str(SAMPLE_RATE),
                "-ac", str(NUM_CHANNELS),
                "-loglevel", "quiet",
                "-",
            ],
            stdout=subprocess.PIPE,
        )
        current_stream = proc

        loop = asyncio.get_event_loop()
        while True:
            data = await loop.run_in_executor(None, proc.stdout.read, BYTES_PER_FRAME)
            if not data or proc != current_stream:
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
        if current_stream and current_stream == proc:
            proc.kill()
            current_stream = None

async def main():
    # connect to LiveKit
    token = (
        api.AccessToken(api_key=API_KEY, api_secret=API_SECRET)
        .with_identity("riffkit-bot")
        .with_name("RiffKit")
        .with_grants(api.VideoGrants(room_join=True, room="music-room"))
        .to_jwt()
    )

    lk_room = rtc.Room()
    await lk_room.connect(LIVEKIT_URL, token)
    print(f"Connected to LiveKit room: {lk_room.name}")

    source = rtc.AudioSource(sample_rate=SAMPLE_RATE, num_channels=NUM_CHANNELS)
    track = rtc.LocalAudioTrack.create_audio_track("music", source)
    await lk_room.local_participant.publish_track(track)

    # connect to Matrix
    matrix = AsyncClient(MATRIX_HOMESERVER, MATRIX_USER_ID)
    await matrix.login(MATRIX_PASSWORD)
    print(f"Logged into Matrix as {MATRIX_USER_ID}")

    async def on_message(room: MatrixRoom, event: RoomMessageText):
        global current_stream

        if event.sender == MATRIX_USER_ID:
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
    await matrix.sync_forever(timeout=30000)


if __name__ == "__main__":
    asyncio.run(main())
