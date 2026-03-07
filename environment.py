import os

from dotenv import load_dotenv

load_dotenv()


MATRIX_HOMESERVER = os.environ["MATRIX_HOMESERVER"]
MATRIX_USER_ID = os.environ["MATRIX_USER_ID"]
MATRIX_PASSWORD = os.environ["MATRIX_PASSWORD"]
MATRIX_ROOM_ID = os.environ["MATRIX_ROOM_ID"]
