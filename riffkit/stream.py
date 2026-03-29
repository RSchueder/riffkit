import asyncio
import glob
import os
import shutil
import subprocess
import tempfile

from livekit import rtc
from nio import AsyncClient  # type: ignore

from riffkit.constants import BYTES_PER_FRAME, NUM_CHANNELS, SAMPLE_RATE
from riffkit.environment import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

current_ydl_proc: subprocess.Popen | None = None
current_stream: subprocess.Popen | None = None


def is_playing() -> bool:
    return current_stream is not None


def stop_stream() -> None:
    global current_stream, current_ydl_proc
    if current_stream:
        current_stream.kill()
        current_stream = None
    if current_ydl_proc:
        current_ydl_proc.kill()
        current_ydl_proc = None


async def stream_audio(
    source: rtc.AudioSource, url: str, matrix_room_id: str, matrix: AsyncClient
):
    global current_stream, current_ydl_proc
    proc = None
    ydl_proc = None
    tmpdir = None

    if current_stream:
        current_stream.kill()
        current_stream = None
    if current_ydl_proc:
        current_ydl_proc.kill()
        current_ydl_proc = None

    try:
        print(f"Starting stream for {url}...")
        loop = asyncio.get_event_loop()

        if "open.spotify.com" in url:
            tmpdir = tempfile.mkdtemp(prefix="riffkit_")

            spotdl_proc = await asyncio.create_subprocess_exec(
                "spotdl",
                "download",
                url,
                "--client-id",
                SPOTIFY_CLIENT_ID,
                "--client-secret",
                SPOTIFY_CLIENT_SECRET,
                "--output",
                os.path.join(tmpdir, "{title}.{output-ext}"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            spotdl_stdout, spotdl_stderr = await asyncio.wait_for(
                spotdl_proc.communicate(), timeout=120
            )
            print(f"spotdl stdout: {spotdl_stdout.decode()}")
            print(f"spotdl stderr: {spotdl_stderr.decode()}")
            print(f"spotdl returncode: {spotdl_proc.returncode}")
            print(f"tmpdir contents: {os.listdir(tmpdir)}")
            if spotdl_proc.returncode != 0:
                raise Exception(f"spotdl failed: {spotdl_stderr.decode()}")

            files = glob.glob(os.path.join(tmpdir, "*"))
            if not files:
                raise Exception("spotdl produced no output file")

            proc = subprocess.Popen(
                [
                    "ffmpeg",
                    "-i",
                    files[0],
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
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        else:
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

        while True:
            assert proc.stdout is not None and proc.stderr is not None
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
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)
