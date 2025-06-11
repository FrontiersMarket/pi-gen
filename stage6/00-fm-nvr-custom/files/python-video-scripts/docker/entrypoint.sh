#!/bin/bash

echo "User/initial dir:"
whoami

# Authenticate with GCS --log-severity=trace
echo "Mounting GCS bucket..."
gcsfuse --implicit-dirs --limit-bytes-per-sec=-1 --limit-ops-per-sec=-1 \
        --stat-cache-max-size-mb=10 --file-cache-max-size-mb=10 --metadata-cache-ttl-secs=10 \
        --file-mode=777 --dir-mode=777 --enable-streaming-writes dagster-bucket-1 /mnt/gcs-bucket
ls -al /mnt/gcs-bucket
sleep 2

#echo "Mount check"
#df -h

# Run the application
#python /app/stitch_videos.py --input-dir /mnt/gcs-bucket/test-in --output test-out --gcs-bucket dagster-bucket-1
time python /app/stitch_videos.py --input-dir /mnt/gcs-bucket/test-in --output /mnt/gcs-bucket/test-out/stitched_video01.mp4 --gcs-bucket dagster-bucket-1 --batchsize 500
sleep 2

df -h
ls -al /mnt/gcs-bucket/test-out/
