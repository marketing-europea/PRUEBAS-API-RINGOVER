import time
from io import BytesIO
from datetime import datetime, time as dtime, timezone
import pandas as pd
import requests
import streamlit as st


DASHBOARD_URL = "https://api-eu.ringover.com/v4/aud/dashboard/currents/calls"
VENTAS_IVR_ID = 11851068

st.title("Test Ringover Dashboard - Ventas")

token = st.text_input("Bearer token de Ringover Dashboard", type="password")

fecha_inicio = st.date_input("Fecha inicio")
fecha_fin = st.date_input("Fecha fin")

limit = st.number_input("Limit count", min_value=1, max_value=500, value=50, step=50)


def fecha_a_ringover_inicio(fecha):
    dt = datetime.combine(fecha, dtime.min).replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", ".000Z")


def fecha_a_ringover_fin(fecha):
    dt = datetime.combine(fecha, dtime.max).replace(tzinfo=timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalizar_call(call):
    queue = call.get("queue") or []
    primer_usuario = queue[0] if queue else {}

    return {
        "call_id": call.get("call_id"),
        "channel_id": call.get("channel_id"),
        "ivr_id": call.get("ivr_id"),
        "type": call.get("type"),
        "direction": call.get("direction"),
        "status": call.get("status"),
        "user_id": primer_usuario.get("user_id"),
        "queue_status": primer_usuario.get("status"),
        "duration_min": (call.get("duration") or 0) / 60,
        "duration_sec": call.get("duration"),
        "creation_date": call.get("creation_date"),
        "bnumber": call.get("bnumber"),
        "onumber": call.get("onumber"),
        "interface": call.get("interface"),
        "is_recording": call.get("is_recording"),
    }


def get_dashboard_calls(token, fecha_inicio, fecha_fin, limit):
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
        "limit_count": int(limit),
        "notes": [],
        "numbers": [],
        "scenarios": [],
        "stars": [],
        "tags": [],
        "transfer_type": None,
        "users": [],
        "start_date": fecha_a_ringover_inicio(fecha_inicio),
        "end_date": fecha_a_ringover_fin(fecha_fin),
    }

    r = requests.post(
        DASHBOARD_URL,
        headers=headers,
        json=payload,
        timeout=30,
    )

    st.write("STATUS:", r.status_code)
    st.write("REQUEST PAYLOAD:")
    st.json(payload)

    if r.status_code != 200:
        st.error("Error llamando al endpoint dashboard")
        st.text(r.text[:5000])
        st.stop()

    data = r.json()

    st.subheader("Respuesta cruda")
    st.json(data)

    call_list = data.get("call_list", [])

    df = pd.DataFrame([normalizar_call(c) for c in call_list])

    return data, df


def calcular_resumen(df):
    if df.empty:
        return pd.DataFrame()

    salientes = df[df["direction"] == "OUT"]
    entrantes = df[df["direction"] == "IN"]

    salientes_conectadas = salientes[salientes["status"] == "ANSWERED"]
    contestadas = df[df["status"] == "ANSWERED"]

    total_llamadas = len(df)
    call_in = len(entrantes)
    call_out = len(salientes)

    time_in = entrantes["duration_min"].sum()
    time_out = salientes["duration_min"].sum()

    return pd.DataFrame([{
        "Total llamadas": total_llamadas,
        "Call in": call_in,
        "Call out": call_out,
        "Conectadas": len(salientes_conectadas),
        "Contestadas": len(contestadas),
        "Contactab.": len(salientes_conectadas) / call_out if call_out else 0,
        "Time in": time_in,
        "Time out": time_out,
        "Mid time": (time_in + time_out) / total_llamadas if total_llamadas else 0,
    }])


if st.button("Probar endpoint dashboard"):
    if not token:
        st.error("Pega el Bearer token.")
        st.stop()

    data, df_calls = get_dashboard_calls(token, fecha_inicio, fecha_fin, limit)
    resumen = calcular_resumen(df_calls)

    st.subheader("Resumen")
    st.dataframe(resumen)

    st.subheader("Llamadas devueltas")
    st.dataframe(df_calls)

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        resumen.to_excel(writer, sheet_name="Resumen", index=False)
        df_calls.to_excel(writer, sheet_name="Calls Dashboard", index=False)

    st.download_button(
        "Descargar Excel prueba",
        data=output.getvalue(),
        file_name="ringover_dashboard_test.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
