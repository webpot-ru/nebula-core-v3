import os
import sys
import json
import time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def get_youtube_service():
    # Read environment variables (GitHub Secrets)
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        print("ERROR: Missing YouTube API credentials in environment variables (YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN).")
        print("Please configure these in GitHub Repository Secrets.")
        return None

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret
    )

    return build("youtube", "v3", credentials=creds)

def upload_video(video_file, title, description, category_id="24", privacy_status="public", tags=None):
    youtube = get_youtube_service()
    if not youtube:
        return False

    if tags is None:
        tags = ["reddit", "redditstories", "askreddit", "viral", "shorts"]

    body = {
        'snippet': {
            'title': title[:100],
            'description': description[:5000],
            'tags': tags,
            'categoryId': category_id
        },
        'status': {
            'privacyStatus': privacy_status,
            'selfDeclaredMadeForKids': False
        }
    }

    print(f"Uploading '{video_file}' to YouTube...")
    media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%")

    print(f"SUCCESS! Video uploaded. Video ID: {response.get('id')}")
    return True

if __name__ == '__main__':
    video_path = sys.argv[1] if len(sys.argv) > 1 else 'final_output.mp4'
    
    story_file = os.path.join(os.path.dirname(__file__), 'story_data.json')
    video_title = "Reddit Story"
    video_desc = "Subscribe for more viral Reddit stories!"
    
    if os.path.exists(story_file):
        with open(story_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            video_title = data.get('title', video_title)
            video_desc = f"{data.get('title')}\n\nOriginal thread: {data.get('url')}\n\n#reddit #shorts #stories"

    if os.path.exists(video_path):
        upload_video(video_path, video_title, video_desc)
    else:
        print(f"Video file '{video_path}' not found. Please render the video first.")
