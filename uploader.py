import os
import sys
import json
import time
import argparse

def get_youtube_service(account_index="1"):
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        print("ERROR: Missing Google YouTube client dependencies. Install requirements.txt first.")
        print(f"Import error: {exc}")
        return None

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

def clean_tags(values, limit=25):
    seen = set()
    tags = []
    for value in values or []:
        tag = str(value).strip().lstrip("#")
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag[:500])
        if len(tags) >= limit:
            break
    return tags


def append_hashtags(description, hashtags):
    active = str(description or "").strip()
    clean = []
    for value in hashtags or []:
        tag = str(value).strip()
        if not tag:
            continue
        tag = tag if tag.startswith("#") else f"#{tag}"
        if tag.lower() not in {existing.lower() for existing in clean}:
            clean.append(tag)
    missing = [tag for tag in clean[:6] if tag.lower() not in active.lower()]
    if missing:
        active = f"{active}\n\n{' '.join(missing)}".strip()
    return active[:5000]


def upload_video(video_file, title, description, account_index="1", category_id="24",
                 privacy_status="public", tags=None, language=None):
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        print("ERROR: Missing google-api-python-client. Install requirements.txt first.")
        print(f"Import error: {exc}")
        return False

    youtube = get_youtube_service(account_index=account_index)
    if not youtube:
        return False

    if tags is None:
        tags = ["reddit", "redditstories", "askreddit", "viral", "shorts"]

    snippet = {
        'title': title[:100],
        'description': description[:5000],
        'tags': clean_tags(tags),
        'categoryId': category_id
    }
    if language:
        snippet['defaultLanguage'] = language
        snippet['defaultAudioLanguage'] = language

    body = {
        'snippet': {
            **snippet
        },
        'status': {
            'privacyStatus': privacy_status,
            'selfDeclaredMadeForKids': False
        }
    }

    print(f"Uploading '{video_file}' to YouTube Account #{account_index} as {privacy_status}...")
    media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%")

    print(f"SUCCESS! Video uploaded. Video ID: {response.get('id')}")
    return True


def load_upload_metadata():
    metadata_file = os.path.join(os.path.dirname(__file__), 'youtube_metadata.json')
    story_file = os.path.join(os.path.dirname(__file__), 'story_data.json')

    video_title = "Reddit Story"
    video_desc = "Subscribe for more viral Reddit stories!"
    tags = None
    language = None

    if os.path.exists(metadata_file):
        with open(metadata_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        video_title = data.get('youtube_title') or video_title
        hashtags = data.get('hashtags') or []
        video_desc = append_hashtags(data.get('youtube_description') or video_desc, hashtags)
        tags = clean_tags((data.get('tags') or []) + (data.get('seo_keywords') or []))
        language = data.get('language') or language
        return video_title, video_desc, tags, language

    if os.path.exists(story_file):
        with open(story_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        video_title = data.get('title', video_title)
        video_desc = f"{data.get('title')}\n\nOriginal thread: {data.get('url')}\n\n#reddit #shorts #stories"

    return video_title, video_desc, tags, language


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Upload rendered video to YouTube.")
    parser.add_argument("video", nargs="?", default="final_output.mp4")
    parser.add_argument("account", nargs="?", default="1")
    parser.add_argument("--privacy-status", default=os.environ.get("YOUTUBE_PRIVACY_STATUS", "public"),
                        choices=["public", "unlisted", "private"])
    parser.add_argument("--category-id", default="24")
    return parser.parse_args(argv)

if __name__ == '__main__':
    args = parse_args(sys.argv[1:])
    video_title, video_desc, video_tags, video_language = load_upload_metadata()

    if os.path.exists(args.video):
        upload_video(
            args.video,
            video_title,
            video_desc,
            account_index=args.account,
            category_id=args.category_id,
            privacy_status=args.privacy_status,
            tags=video_tags,
            language=video_language,
        )
    else:
        print(f"Video file '{args.video}' not found. Please render the video first.")
