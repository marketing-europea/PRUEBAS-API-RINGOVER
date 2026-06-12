import requests
import json

API_KEY = "TU_API_KEY"

r = requests.get(
    "https://public-api.ringover.com/v2/calls",
    headers={
        "Authorization": API_KEY
    },
    params={
        "limit_count": 1
    }
)

print("STATUS:", r.status_code)
print(json.dumps(r.json(), indent=2, ensure_ascii=False))
