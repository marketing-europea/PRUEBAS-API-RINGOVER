import requests

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
print("CONTENT TYPE:", r.headers.get("content-type"))
print("RESPUESTA:")
print(r.text[:5000])
