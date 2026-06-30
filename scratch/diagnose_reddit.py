import os
import requests

print("=== Reddit GitHub Actions Diagnostic ===")

# Try to get variables
client_id = os.environ.get("REDDIT_CLIENT_ID", "")
client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
username = os.environ.get("REDDIT_USERNAME", "")
password = os.environ.get("REDDIT_PASSWORD", "")

print(f"REDDIT_CLIENT_ID length: {len(client_id)}")
print(f"REDDIT_CLIENT_SECRET length: {len(client_secret)}")
print(f"REDDIT_USERNAME: '{username}'")
print(f"REDDIT_PASSWORD length: {len(password)}")

# Apps to test
apps = [
    {
        "name": "red 2025",
        "client_id": "JYA8zMAO2b1GTIZnHoITbg",
        "client_secret": "kKDnjQmqAidycdvliILdPvoMq15w_A"
    },
    {
        "name": "lalishka",
        "client_id": "8wAEkIwJOrlpi82dyp5kaA",
        "client_secret": "PN7uexxeuTWkxXPJsFuSXny6DPG7Kw"
    },
    {
        "name": "GitHub Secret App",
        "client_id": client_id,
        "client_secret": client_secret
    }
]

for app in apps:
    if not app["client_id"] or not app["client_secret"]:
        print(f"\nSkipping {app['name']} (missing credentials)")
        continue
        
    print(f"\nTesting: {app['name']} ({app['client_id'][:5]}...)")
    
    # 1. Test script auth
    url = "https://www.reddit.com/api/v1/access_token"
    headers = {"User-Agent": f"script:{app['name']}:v1.0 (by /u/{username})"}
    data = {
        "grant_type": "password",
        "username": username,
        "password": password
    }
    auth = (app["client_id"], app["client_secret"])
    
    try:
        r = requests.post(url, headers=headers, data=data, auth=auth, timeout=10)
        print(f"  Auth Status: {r.status_code}")
        res = r.json()
        if "access_token" in res:
            print("  ✅ SUCCESS! Obtained access token.")
            # Test reading
            token = res["access_token"]
            get_headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": f"script:{app['name']}:v1.0 (by /u/{username})"
            }
            sub_r = requests.get(
                "https://oauth.reddit.com/r/AmItheAsshole/top.json?limit=1",
                headers=get_headers,
                timeout=10
            )
            print(f"  Fetch Subreddit Status: {sub_r.status_code}")
            if sub_r.status_code == 200:
                print("  ✅ Read successful!")
                posts = sub_r.json().get("data", {}).get("children", [])
                if posts:
                    print(f"  Post: {posts[0]['data']['title']}")
        else:
            print(f"  ❌ Failed. Response: {res}")
    except Exception as e:
        print(f"  Error: {e}")
