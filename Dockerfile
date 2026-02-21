FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# install dependencies separately from code so this layer is cached
COPY requirements.txt .
RUN pip install -r requirements.txt
