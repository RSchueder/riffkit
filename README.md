# riffkit
An element music bot

# Testing

```
docker compose up -d

```

then

```
lk room join  \
    --url ws://localhost:7880 \
    --api-key <key> \
    --api-secret <secret> \
    --auto-subscribe test-room
```

then inside container

```
python generate_room_url.py
```

Then go to this URL. Then in a room with your bot invited, type 

`!play <URL>` and the audio should stream.