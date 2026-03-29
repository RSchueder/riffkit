FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt .
COPY constraints.txt .
RUN pip install -r requirements.txt -c constraints.txt
RUN sed -i \
  "s/raw_album_meta\[\"genres\"\] + raw_artist_meta\[\"genres\"\]/raw_album_meta.get(\"genres\", []) + raw_artist_meta.get(\"genres\", [])/g" \
  /usr/local/lib/python3.12/site-packages/spotdl/types/song.py && \
  sed -i \
  "s/raw_album_meta\[\"label\"\]/raw_album_meta.get(\"label\", \"\")/g" \
  /usr/local/lib/python3.12/site-packages/spotdl/types/song.py && \
  sed -i \
  "s/raw_track_meta\[\"popularity\"\]/raw_track_meta.get(\"popularity\", 0)/g" \
  /usr/local/lib/python3.12/site-packages/spotdl/types/song.py
COPY . .