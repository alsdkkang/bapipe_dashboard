FROM python:3.11-slim

# System libraries: ffmpeg (imageio video export), libGL/glib (opencv),
# HDF5 (pytables), all required by gui_app/requirements.txt at import time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libgl1 libglib2.0-0 libhdf5-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first for layer caching.
COPY gui_app/requirements.txt /app/gui_app/requirements.txt
RUN pip install --no-cache-dir -r /app/gui_app/requirements.txt

# App + bapipe library source (imported via sys.path in app.py).
COPY src /app/src
COPY gui_app /app/gui_app
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Ephemeral state dir (HF Spaces resets it; mount a volume elsewhere for durability).
ENV BAPIPE_RECORDS_DIR=/data/records \
    BAPIPE_USERS_FILE=/data/users.json \
    BAPIPE_ACCESS_FILE=/data/access.json \
    PORT=7860
RUN mkdir -p /data/records && chmod -R 777 /data

EXPOSE 7860
ENTRYPOINT ["/app/entrypoint.sh"]
