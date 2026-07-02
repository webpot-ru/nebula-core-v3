import os
client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
if client_id:
    # Print the prefix (project number)
    parts = client_id.split("-")
    if len(parts) > 1:
        print(f"Google Cloud Project Number (prefix): {parts[0]}")
    else:
        print(f"Google Cloud Client ID Prefix: {client_id[:25]}...")
else:
    print("YOUTUBE_CLIENT_ID is not set.")
