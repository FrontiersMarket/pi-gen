# Use Python base image with FFmpeg installed
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    curl gnupg ca-certificates fuse ffmpeg \
    && echo "deb http://packages.cloud.google.com/apt gcsfuse-bookworm main" | tee /etc/apt/sources.list.d/gcsfuse.list \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - \
    && apt-get update && apt-get install -y gcsfuse \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install dependencies
RUN pip install google-cloud-storage

# Create a mount directory
RUN mkdir /mnt/gcs-bucket

# Set the entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy app
COPY stitch_videos.py /app/

# Create a non-root user and switch to it
#RUN groupadd -r dagster && useradd -r -g dagster dagster

# Ensure the non-root user has necessary permissions
#RUN chown -R dagster:dagster /app /mnt/gcs-bucket

# Switch to the non-root user
#USER dagster

# Run the entrypoint script
CMD ["/entrypoint.sh"]
