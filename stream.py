import asyncio
import subprocess

import yt_dlp
from livekit import api, rtc

from environment import API_KEY, API_SECRET, LIVEKIT_URL

SAMPLE_RATE = 48000
NUM_CHANNELS = 1
SAMPLES_PER_CHANNEL = 480  # 10ms per frame
BYTES_PER_FRAME = SAMPLES_PER_CHANNEL * 2  # 16-bit = 2 bytes per sample


def resolve_stream_url(url: str) -> str:
    with yt_dlp.YoutubeDL({"format": "bestaudio", "quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        return info["url"]


async def stream_audio(source: rtc.AudioSource, stream_url: str):
    ffmpeg = subprocess.Popen(
        [
            "ffmpeg",
            "-i",
            stream_url,
            "-f",
            "s16le",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            str(NUM_CHANNELS),
            "-loglevel",
            "quiet",
            "-",
        ],
        stdout=subprocess.PIPE,
    )

    loop = asyncio.get_event_loop()

    try:
        while True:
            # read in executor so we don't block the event loop
            data = await loop.run_in_executor(None, ffmpeg.stdout.read, BYTES_PER_FRAME)
            if not data:
                break
            frame = rtc.AudioFrame(
                data=data,
                sample_rate=SAMPLE_RATE,
                num_channels=NUM_CHANNELS,
                samples_per_channel=len(data) // 2,
            )
            await source.capture_frame(frame)
    finally:
        ffmpeg.kill()


async def main():
    url = input("Enter a YouTube (or other) URL: ").strip()

    print("Resolving stream URL...")
    stream_url = resolve_stream_url(url)
    print(f"Got stream URL, connecting to LiveKit...")

    token = (
        api.AccessToken(api_key=API_KEY, api_secret=API_SECRET)
        .with_identity("test-bot")
        .with_name("Test Bot")
        .with_grants(api.VideoGrants(room_join=True, room="test-room"))
        .to_jwt()
    )

    room = rtc.Room()
    await room.connect(LIVEKIT_URL, token)
    print(f"Connected to room: {room.name}")

    source = rtc.AudioSource(sample_rate=SAMPLE_RATE, num_channels=NUM_CHANNELS)
    track = rtc.LocalAudioTrack.create_audio_track("music", source)
    await room.local_participant.publish_track(track)
    print("Streaming audio... Ctrl+C to stop.")

    try:
        await stream_audio(source, stream_url)
    except KeyboardInterrupt:
        pass

    print("Disconnecting...")
    await room.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
