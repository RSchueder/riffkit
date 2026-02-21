import os

from dotenv import load_dotenv

load_dotenv()


LIVEKIT_URL = os.environ["LIVEKIT_URL"]
API_KEY = os.environ["LIVEKIT_API_KEY"]
API_SECRET = os.environ["LIVEKIT_API_SECRET"]

MATRIX_HOMESERVER = os.environ["MATRIX_HOMESERVER"]
MATRIX_USER_ID = os.environ["MATRIX_USER_ID"]
MATRIX_PASSWORD = os.environ["MATRIX_PASSWORD"]
