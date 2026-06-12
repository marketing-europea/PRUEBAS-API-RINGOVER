import requests

API_KEY = "9100d3646e618b7526417ada74853f620bcfa288"

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
print("CONTENT-TYPE:", r.headers.get("Content-Type"))
print("RESPUESTA:")
print(r.text[:5000])
