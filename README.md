# riffkit
An element music bot

# Testing

```
docker compose up -d bot

```
then inside container

```
python stream.py
```

then outside container

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