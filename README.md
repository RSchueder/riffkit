# riffkit
An [Element](https://element.io/en) music bot that can stream from:
* youtube
* spotify

**This is a work in progress and is not ready for general use.**

# Getting started

## Config
Your `.env` file should be populated with the following environment variables:
```
MATRIX_HOMESERVER=https://matrix.org
MATRIX_USER_ID=@******:matrix.org
MATRIX_PASSWORD=******
MATRIX_ROOM_ID=!******:matrix.org
SPOTIFY_CLIENT_ID=******
SPOTIFY_CLIENT_SECRET=******
SPOTIFY_USE_YOUTUBE=true  # or false
```

## Running

```
docker compose build
docker compose up bot
```

# Bot commands
You can use these commands in the Element room chat to control the bot:

* `!play` - plays a song, playlist or album
* `!stop` - stops the current queue
* `!next` - skips the current song, plays the next song in the queue
* `!queue` - shows the current queue
