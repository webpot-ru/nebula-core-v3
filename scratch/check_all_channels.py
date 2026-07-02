import sys
import os
import json

# Add parent directory to path so we can import uploader
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from uploader import check_channel_mapping, UploadError

print("=== Checking All 7 YouTube Channel Mappings ===")

success = True
for i in range(1, 8):
    try:
        info = check_channel_mapping(str(i))
        print(f"✅ Account #{i} SUCCESS:")
        print(f"   Title:  {info.get('title')}")
        print(f"   Handle: {info.get('customUrl') or '(no handle)'}")
        print(f"   ID:     {info.get('id')}")
    except UploadError as exc:
        print(f"❌ Account #{i} FAILED: {exc}")
        success = False
    except Exception as exc:
        print(f"❌ Account #{i} ERROR: {exc}")
        success = False

if not success:
    print("\n⚠️ Some channels failed verification. Please review the errors above.")
    sys.exit(1)
else:
    print("\n🎉 ALL 7 CHANNELS ARE SUCCESSFULLY VERIFIED AND READY!")
