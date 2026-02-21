import os

from dotenv import load_dotenv

load_dotenv()

LIVEKIT_URL = os.environ.get("LIVEKIT_URL")
API_KEY = os.environ.get("LIVEKIT_API_KEY")
API_SECRET = os.environ.get("LIVEKIT_API_SECRET")
