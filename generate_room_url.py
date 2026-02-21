from livekit import api

from environment import API_KEY, API_SECRET

token = (
    api.AccessToken(api_key=API_KEY, api_secret=API_SECRET)
    .with_identity("listener")
    .with_name("Listener")
    .with_grants(api.VideoGrants(room_join=True, room="music-room"))
    .to_jwt()
)
print(f"https://meet.livekit.io/custom?liveKitUrl=ws://localhost:7880&token={token}")
