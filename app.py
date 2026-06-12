import streamlit as st
import requests

API_KEY = "9100d3646e618b7526417ada74853f620bcfa288"

st.title("Prueba Ringover")

r = requests.get(
    "https://public-api.ringover.com/v2/calls",
    headers={"Authorization": API_KEY},
    params={"limit_count": 1}
)

st.write("STATUS:", r.status_code)
st.write("CONTENT TYPE:", r.headers.get("content-type"))
st.text(r.text[:5000])
