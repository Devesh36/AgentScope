import json
import urllib.request

with urllib.request.urlopen(
    "http://127.0.0.1:8000/health/ready", timeout=5
) as response:
    data = json.load(response)
    if data.get("status") != "ready" or data.get("storage") != "postgresql":
        raise SystemExit("API is not ready with PostgreSQL")
