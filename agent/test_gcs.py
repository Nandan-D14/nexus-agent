"""Quick test: can we reach GCS with the SA key?"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

from nexus.config import settings, AGENT_DIR
from pathlib import Path

print("=== Config ===")
print(f"GOOGLE_APPLICATION_CREDENTIALS = {settings.google_application_credentials}")
print(f"GOOGLE_PROJECT_ID = {settings.google_project_id}")
print(f"FIREBASE_PROJECT_ID = {settings.firebase_project_id}")

# Force reload the storage module to pick up changes
import importlib
import nexus.storage
importlib.reload(nexus.storage)

print("\n=== Testing GCS ===")
try:
    from nexus.storage import get_storage_client, get_artifact_bucket_name
    client = get_storage_client()
    print(f"Storage client project: {client.project}")
    print(f"Credentials type: {type(client._credentials)}")
    
    bucket_name = get_artifact_bucket_name()
    print(f"Bucket name: {bucket_name}")
    
    try:
        bucket = client.get_bucket(bucket_name)
        print(f"[OK] Bucket exists: {bucket.name}")
    except Exception as e:
        print(f"[FAIL] Bucket access failed: {e}")
        print(f"Attempting to create bucket...")
        try:
            bucket = client.create_bucket(bucket_name, location="US")
            print(f"[OK] Bucket created: {bucket.name}")
        except Exception as ce:
            print(f"[FAIL] Bucket creation failed: {ce}")
            sys.exit(1)

    # Test upload
    print("\n=== Testing Upload ===")
    from nexus.storage import upload_artifact
    url = upload_artifact("test-session", "test-run", "test.txt", b"hello world")
    print(f"Upload result URL: {url[:100] if url else None}...")
    if url:
        print("[OK] Upload WORKS!")
    else:
        print("[FAIL] Upload returned None")
        
except Exception as e:
    import traceback
    print(f"[FAIL] Error: {e}")
    traceback.print_exc()
