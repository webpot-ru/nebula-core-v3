import os
import sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

print("=== Checking Uploaded Video Privacy & Verification Status ===")

client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
# We uploaded to Account #4
refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN_ACC4", "")

if not client_id or not client_secret or not refresh_token:
    print("❌ Missing YouTube credentials for Account 4.")
    sys.exit(1)

try:
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret
    )
    youtube = build("youtube", "v3", credentials=creds)
    
    # Query status of our uploaded video Og0ZYnseVbk
    video_id = "Og0ZYnseVbk"
    print(f"Querying YouTube API for Video ID: {video_id}...")
    res = youtube.videos().list(
        part="status,snippet",
        id=video_id
    ).execute()
    
    items = res.get("items", [])
    if not items:
        print(f"❌ Video {video_id} not found or inaccessible.")
        sys.exit(0)
        
    video = items[0]
    status = video.get("status", {})
    snippet = video.get("snippet", {})
    
    print("\n✅ API Response Details:")
    print(f"  Title: {snippet.get('title')}")
    print(f"  Privacy Status: {status.get('privacyStatus')}")
    print(f"  Upload Status: {status.get('uploadStatus')}")
    print(f"  Rejection Reason: {status.get('rejectionReason', 'None')}")
    print(f"  Privacy Status User Flow: {status.get('publicStatsViewable', 'unknown')}")
    
    if status.get("privacyStatus") == "private" and status.get("rejectionReason") == "uploaderIsNotVerified":
         print("\n⚠️ VERIFICATION REQUIRED:")
         print("  YouTube locked this video to Private because the Google Cloud App is in 'Testing' mode (unverified).")
    else:
         print("\n✨ App Status is OK or video has different status.")
         
except Exception as e:
    print(f"❌ Error querying video status: {e}")
