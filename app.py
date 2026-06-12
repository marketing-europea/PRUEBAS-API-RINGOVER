import requests
import streamlit as st
from datetime import datetime, time as dtime, timezone

URL = "https://api-eu.ringover.com/v4/aud/dashboard/stats/calls/global"
VENTAS_IVR_ID = 11851068

st.title("Test stats global Ringover")

token = st.text_input("Bearer token", type="password")
fecha_inicio = st.date_input("Fecha inicio")
fecha_fin = st.date_input("Fecha fin")

def fecha_inicio_z(fecha):
    return datetime.combine(fecha, dtime.min).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", ".000Z")

def fecha_fin_z(fecha):
    return datetime.combine(fecha, dtime.max).replace(tzinfo=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

if st.button("Probar"):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "*/*",
    }

    payload = {
        "accounts": [],
        "alpha2_codes": [],
        "call_type": [],
        "channels": [],
        "contexts_with_states": [],
        "filter": "ALL",
        "groups": [],
        "handle_call": "all",
        "handle_call_response_type": ["CALL", "SMS", "EMAIL", "AVOID"],
        "history_scope": [],
        "ivrs": [VENTAS_IVR_ID],
        "notes": [],
        "numbers": [],
        "scenarios": [],
        "stars": [],
        "tags": [],
        "transfer_type": None,
        "users": [],
        "start_date": fecha_inicio_z(fecha_inicio),
        "end_date": fecha_fin_z(fecha_fin),
    }

    r = requests.post(URL, headers=headers, json=payload)

    st.write("STATUS:", r.status_code)
    st.subheader("Payload")
    st.json(payload)

    st.subheader("Response")
    if r.headers.get("content-type", "").startswith("application/json"):
        st.json(r.json())
    else:
        st.text(r.text[:5000])
