import os
import requests
from datetime import datetime, timedelta
from google.cloud import storage

def trigger_video_stitch(event, context):
    """Cloud Function to trigger video stitching for the previous day.
    
    Args:
        event (dict): The dictionary with data specific to this type of event.
        context (google.cloud.functions.Context): The Cloud Functions event
            metadata.
    """
    # Get Cloud Run service URL from environment variable
    service_url = os.environ.get('STITCH_SERVICE_URL')
    if not service_url:
        raise ValueError("STITCH_SERVICE_URL environment variable not set")
    
    # Get yesterday's date
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # List of prefixes to process
    prefixes = ['calf_counting_cam', 'calf_face_cam']
    bucket_name = os.environ.get('BUCKET_NAME', 'video_upload_test')
    
    for prefix in prefixes:
        # Call the Cloud Run service
        response = requests.post(
            service_url,
            json={
                'bucket': bucket_name,
                'prefix': prefix,
                'date': yesterday
            }
        )
        
        if response.status_code != 200:
            print(f"Error processing {prefix} for {yesterday}: {response.text}")
        else:
            result = response.json()
            print(f"Successfully processed {prefix} for {yesterday}:")
            print(f"- Segments processed: {result['segments_processed']}")
            print(f"- Output URL: {result['url']}")
