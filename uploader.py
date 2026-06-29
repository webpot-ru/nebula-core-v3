import os
import sys
import json
import time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def get_youtube_service(account_index="1"):
    # Read environment variables (GitHub Secrets) for specific account
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    
    # Try account specific token first, fallback to standard YOUTUBE_REFRESH_TOKEN
    token_env_var = f"YOUTUBE_REFRESH_TOKEN_ACC{account_index}"
    refresh_token = os.environ.get(token_env_var) or os.environ.get("YOUTUBE_REFRESH_TOKEN")

    if not client_id or not client_secret or not refresh_token:
        print(f"ERROR: Missing YouTube API credentials for Account {account_index}.")
        print(f"Looking for env vars: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and {token_env_var} (or YOUTUBE_REFRESH_TOKEN).")
        return None

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret
    )

    return build("youtube", "v3", credentials=creds)

def upload_video(video_file, title, description, account_index="1", category_id="24", privacy_status="public", tags=None):
    youtube = get_youtube_service(account_index=account_index)
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

    print(f"Uploading '{video_file}' to YouTube Account #{account_index}...")
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
    acc_num = sys.argv[2] if len(sys.argv) > 3 else "1"
    
    story_file = os.path.join(os.path.dirname(__file__), 'story_data.json')
    video_title = "Reddit Story"
    video_desc = "Subscribe for more viral Reddit stories!"
    
    if os.path.exists(story_file):
        with open(story_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            video_title = data.get('title', video_title)
            video_desc = f"{data.get('title')}\n\nOriginal thread: {data.get('url')}\n\n#reddit #shorts #stories"

    if os.path.exists(video_path):
        upload_video(video_path, video_title, video_desc, account_index=acc_num)
    else:
        print(f"Video file '{video_path}' not found. Please render the video first.")
