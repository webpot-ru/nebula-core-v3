import os
import sys
import json
import time
import argparse
import hashlib
from pathlib import Path


class UploadError(RuntimeError):
    pass


YOUTUBE_RESUMABLE_CHUNK_SIZE = 8 * 1024 * 1024


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_upload_state(path, payload):
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)

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


def get_youtube_oauth_scopes(account_index="1"):
    import requests

    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    token_env_var = f"YOUTUBE_REFRESH_TOKEN_ACC{account_index}"
    refresh_token = os.environ.get(token_env_var) or os.environ.get("YOUTUBE_REFRESH_TOKEN")

    if not client_id or not client_secret or not refresh_token:
        raise UploadError(
            f"Missing YouTube API credentials for Account {account_index}. "
            f"Need YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and {token_env_var}."
        )

    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if response.status_code >= 400:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        message = payload.get("error_description") or payload.get("error") or response.text[:300]
        raise UploadError(f"OAuth token refresh failed ({response.status_code}): {message}")

    payload = response.json()
    scopes = sorted(str(payload.get("scope") or "").split())
    print(
        "Verified OAuth token scopes: "
        f"Account #{account_index} -> {', '.join(scopes) if scopes else '(scope not returned)'}"
    )
    return scopes


def load_expected_channel(account_index="1"):
    channel_id = f"acc{account_index}"
    config_path = Path(__file__).with_name("channels.json")
    if not config_path.exists():
        raise UploadError("channels.json is required for YouTube account verification.")
    with config_path.open("r", encoding="utf-8") as f:
        channels = json.load(f).get("channels", [])
    for channel in channels:
        if channel.get("id") == channel_id:
            return channel
    raise UploadError(f"channels.json has no channel config for {channel_id}.")


def normalize_channel_value(value):
    text = str(value or "").strip().lower()
    if text.startswith("https://www.youtube.com/"):
        text = text.rsplit("/", 1)[-1]
    if text.startswith("youtube.com/"):
        text = text.rsplit("/", 1)[-1]
    return text.lstrip("@")


def authenticated_channel_info(youtube):
    response = youtube.channels().list(
        part="snippet",
        mine=True,
        maxResults=1,
    ).execute()
    items = response.get("items") or []
    if not items:
        raise UploadError("YouTube account verification failed: channels.list(mine=true) returned no channels.")

    channel = items[0]
    snippet = channel.get("snippet") or {}
    return {
        "id": channel.get("id") or "",
        "title": snippet.get("title") or "",
        "customUrl": snippet.get("customUrl") or "",
        "defaultLanguage": snippet.get("defaultLanguage") or "",
        "country": snippet.get("country") or "",
    }


def verify_account_channel(youtube, expected_channel, account_index="1"):
    actual = authenticated_channel_info(youtube)
    expected_id = str(expected_channel.get("youtube_channel_id") or "").strip()
    expected_handle = normalize_channel_value(expected_channel.get("handle"))
    expected_name = str(expected_channel.get("name") or "").strip()

    actual_id = str(actual.get("id") or "").strip()
    actual_handle = normalize_channel_value(actual.get("customUrl"))
    actual_title = str(actual.get("title") or "").strip()

    matches_id = bool(expected_id and actual_id == expected_id)
    matches_handle = bool(expected_handle and actual_handle == expected_handle)
    matches_title = bool(expected_name and actual_title.casefold() == expected_name.casefold())

    if not (matches_id or matches_handle or matches_title):
        expected_label = expected_channel.get("handle") or expected_name or expected_channel.get("id")
        actual_label = actual.get("customUrl") or actual_title or actual_id or "unknown"
        raise UploadError(
            f"YouTube account mismatch for Account #{account_index}: "
            f"token resolves to {actual_label!r} ({actual_title}, {actual_id}), "
            f"expected {expected_label!r}. Upload blocked before spending quota."
        )

    print(
        "Verified YouTube account mapping: "
        f"Account #{account_index} -> {actual_title} "
        f"({actual.get('customUrl') or actual_id})"
    )
    return actual


def check_channel_mapping(account_index="1"):
    youtube = get_youtube_service(account_index=account_index)
    if not youtube:
        raise UploadError("Could not create YouTube API service.")
    expected_channel = load_expected_channel(account_index)
    return verify_account_channel(youtube, expected_channel, account_index)

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
                 privacy_status="public", tags=None, language=None,
                 verify_channel=True, thumbnail_file=None, caption_file=None,
                 caption_language=None, caption_name=None, result_path=None):
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        print("ERROR: Missing google-api-python-client. Install requirements.txt first.")
        print(f"Import error: {exc}")
        return False

    youtube = get_youtube_service(account_index=account_index)
    if not youtube:
        raise UploadError("Could not create YouTube API service.")

    channel_info = None
    if verify_channel:
        expected_channel = load_expected_channel(account_index)
        channel_info = verify_account_channel(youtube, expected_channel, account_index)

    thumbnail_path = None
    if thumbnail_file:
        thumbnail_path = Path(thumbnail_file)
        if not thumbnail_path.is_file():
            raise UploadError(f"Thumbnail file not found: {thumbnail_file}")

    caption_path = None
    if caption_file:
        caption_path = Path(caption_file)
        if not caption_path.is_file():
            raise UploadError(f"Caption file not found: {caption_file}")
        caption_language = str(caption_language or language or "").strip()
        if not caption_language:
            raise UploadError("Caption language is required when a caption file is provided.")
        caption_name = str(caption_name or caption_language).strip()[:150]

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
    media = MediaFileUpload(
        video_file,
        chunksize=YOUTUBE_RESUMABLE_CHUNK_SIZE,
        resumable=True,
    )
    request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%")

    video_id = response.get('id')
    if not video_id:
        raise UploadError("YouTube upload response did not contain a video id.")
    print(f"SUCCESS! Video uploaded. Video ID: {video_id}")

    state = {
        "version": 1,
        "status": "VIDEO_CREATED",
        "video_id": video_id,
        "privacy_status_requested": privacy_status,
        "video_sha256": _sha256_file(video_file),
        "thumbnail_sha256": (
            _sha256_file(thumbnail_file) if thumbnail_file else None
        ),
        "caption_sha256": (
            _sha256_file(caption_file) if caption_file else None
        ),
    }
    _write_upload_state(result_path, state)

    readback = read_video_metadata(youtube, video_id)
    if readback:
        snippet_readback = readback.get("snippet") or {}
        status_readback = readback.get("status") or {}
        print(
            "Verified uploaded video readback: "
            f"channelId={snippet_readback.get('channelId')}, "
            f"privacy={status_readback.get('privacyStatus')}, "
            f"language={snippet_readback.get('defaultLanguage') or snippet_readback.get('defaultAudioLanguage') or 'unset'}"
        )
        if channel_info and snippet_readback.get("channelId") != channel_info.get("id"):
            raise UploadError(
                f"Uploaded video channel mismatch: readback channelId={snippet_readback.get('channelId')} "
                f"but preflight channelId={channel_info.get('id')}."
            )
        if status_readback.get("privacyStatus") != privacy_status:
            raise UploadError(
                "Uploaded video privacy mismatch: "
                f"readback={status_readback.get('privacyStatus')} requested={privacy_status}."
            )

    thumbnail_response = None
    if thumbnail_path:
        thumbnail_response = youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumbnail_path), resumable=False),
        ).execute()
        if not isinstance(thumbnail_response, dict):
            raise UploadError("YouTube thumbnail upload returned an invalid response.")

    caption_id = None
    caption_readback = None
    if caption_path:
        caption_response = youtube.captions().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "language": caption_language,
                    "name": caption_name,
                    "isDraft": False,
                },
            },
            media_body=MediaFileUpload(
                str(caption_path),
                mimetype="application/octet-stream",
                resumable=False,
            ),
        ).execute()
        caption_id = (caption_response or {}).get("id")
        if not caption_id:
            raise UploadError("YouTube caption upload response did not contain a caption id.")
        caption_items = youtube.captions().list(
            part="snippet",
            videoId=video_id,
            id=caption_id,
        ).execute().get("items") or []
        if not caption_items:
            raise UploadError("YouTube caption readback returned no matching track.")
        caption_readback = caption_items[0].get("snippet") or {}
        if caption_readback.get("videoId") != video_id:
            raise UploadError("YouTube caption readback resolved to another video.")
        if caption_readback.get("language") != caption_language:
            raise UploadError(
                "YouTube caption language mismatch: "
                f"readback={caption_readback.get('language')} requested={caption_language}."
            )

    snippet_readback = (readback or {}).get("snippet") or {}
    status_readback = (readback or {}).get("status") or {}
    state.update({
        "status": "COMPLETE",
        "channel_id": snippet_readback.get("channelId"),
        "privacy_status_readback": status_readback.get("privacyStatus"),
        "thumbnail_uploaded": thumbnail_file is not None,
        "caption_uploaded": caption_file is not None,
        "caption_id": caption_id,
        "caption_language_readback": (
            caption_readback.get("language") if caption_readback else None
        ),
    })
    _write_upload_state(result_path, state)
    return response


def read_video_metadata(youtube, video_id):
    response = youtube.videos().list(
        part="snippet,status",
        id=video_id,
        maxResults=1,
    ).execute()
    items = response.get("items") or []
    if not items:
        raise UploadError(f"YouTube readback failed: videos.list returned no item for {video_id}.")
    return items[0]


def load_upload_metadata(metadata_file=None, story_file=None):
    metadata_file = metadata_file or os.path.join(os.path.dirname(__file__), 'youtube_metadata.json')
    story_file = story_file or os.path.join(os.path.dirname(__file__), 'story_data.json')

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
    parser.add_argument("--account-index", help="YouTube account index override, useful with --check-channel-only.")
    parser.add_argument("--privacy-status", default=os.environ.get("YOUTUBE_PRIVACY_STATUS", "public"),
                        choices=["public", "unlisted", "private"])
    parser.add_argument("--category-id", default="24")
    parser.add_argument("--metadata-file", help="Exact metadata JSON to upload.")
    parser.add_argument("--thumbnail-file", help="Exact custom thumbnail to upload after the video.")
    parser.add_argument("--caption-file", help="Exact SRT/VTT caption track to upload after the video.")
    parser.add_argument("--caption-language", help="BCP-47 language for --caption-file.")
    parser.add_argument("--caption-name", help="Viewer-facing name for --caption-file.")
    parser.add_argument("--result", help="Atomically persist upload id, hashes, privacy, and readback state.")
    parser.add_argument(
        "--check-channel-only",
        action="store_true",
        help="Verify the authenticated YouTube account against channels.json and exit without uploading.",
    )
    parser.add_argument(
        "--check-token-scopes-only",
        action="store_true",
        help="Refresh the account token and print granted OAuth scopes without uploading.",
    )
    parser.add_argument(
        "--skip-channel-check",
        action="store_true",
        help="Disable channels.json vs authenticated YouTube channel preflight. Use only for emergency manual recovery.",
    )
    return parser.parse_args(argv)

if __name__ == '__main__':
    args = parse_args(sys.argv[1:])
    account_index = args.account_index or args.account

    if args.check_token_scopes_only:
        try:
            scopes = get_youtube_oauth_scopes(account_index)
            print(json.dumps({"status": "ok", "account": account_index, "scopes": scopes}, ensure_ascii=False, indent=2))
            sys.exit(0)
        except UploadError as exc:
            print(f"ERROR: {exc}")
            sys.exit(1)
        except Exception as exc:
            print(f"ERROR: YouTube OAuth scope check failed: {exc}")
            sys.exit(1)

    if args.check_channel_only:
        try:
            info = check_channel_mapping(account_index)
            print(json.dumps({"status": "ok", "account": account_index, "channel": info}, ensure_ascii=False, indent=2))
            sys.exit(0)
        except UploadError as exc:
            print(f"ERROR: {exc}")
            sys.exit(1)
        except Exception as exc:
            print(f"ERROR: YouTube account verification failed: {exc}")
            sys.exit(1)

    video_title, video_desc, video_tags, video_language = load_upload_metadata(
        metadata_file=args.metadata_file,
    )

    if not os.path.exists(args.video):
        print(f"Video file '{args.video}' not found. Please render the video first.")
        sys.exit(1)

    try:
        upload_video(
            args.video,
            video_title,
            video_desc,
            account_index=account_index,
            category_id=args.category_id,
            privacy_status=args.privacy_status,
            tags=video_tags,
            language=video_language,
            verify_channel=not args.skip_channel_check,
            thumbnail_file=args.thumbnail_file,
            caption_file=args.caption_file,
            caption_language=args.caption_language,
            caption_name=args.caption_name,
            result_path=args.result,
        )
    except UploadError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
