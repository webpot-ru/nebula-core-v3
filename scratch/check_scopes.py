import os
import requests

print("=== Checking YouTube Account OAuth Scopes ===")

client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")

print(f"YOUTUBE_CLIENT_ID length: {len(client_id)}")
print(f"YOUTUBE_CLIENT_SECRET length: {len(client_secret)}")

for i in range(1, 8):
    token_env_name = f"YOUTUBE_REFRESH_TOKEN_ACC{i}"
    refresh_token = os.environ.get(token_env_name, "")
    
    if not refresh_token:
        print(f"Account #{i} ({token_env_name}): ❌ Not set in secrets")
        continue
        
    print(f"Account #{i}: Found refresh token (length: {len(refresh_token)}). Querying Google...")
    
    try:
        # Request a fresh access token to see what scopes are active
        res = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            },
            timeout=10
        )
        
        if res.status_code == 200:
            payload = res.json()
            scopes = payload.get("scope", "")
            print(f"  ✅ SUCCESS! Authorized scopes:")
            for scope in sorted(scopes.split(" ")):
                if scope:
                    print(f"    - {scope}")
        else:
            print(f"  ❌ FAILED (HTTP {res.status_code}): {res.text[:500]}")
            
    except Exception as e:
        print(f"  Error: {e}")
