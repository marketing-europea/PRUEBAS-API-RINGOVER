import time
from io import BytesIO
from datetime import datetime, time as dtime, timezone

import requests
import pandas as pd
import streamlit as st


API_KEY = "9100d3646e618b7526417ada74853f620bcfa288"
BASE_URL = "https://public-api.ringover.com/v2"

HEADERS = {
    "Authorization": API_KEY
}


st.title("KPIs Ringover - Ventas")

fecha_inicio = st.date_input("Fecha inicio")
fecha_fin = st.date_input("Fecha fin")
ivr_name = st.text_input("Centralita / IVR", value="Ventas")


def segundos_a_minutos(valor):
    if valor is None:
        return 0
    return float(valor) / 60


def parse_fecha_ringover(valor):
    if not valor:
        return None
    return datetime.fromisoformat(valor.replace("Z", "+00:00"))


def get_calls_sin_fechas(fecha_inicio, fecha_fin):
    llamadas = []
    offset = 0
    limit = 100

    inicio_dt = datetime.combine(fecha_inicio, dtime.min).replace(tzinfo=timezone.utc)
    fin_dt = datetime.combine(fecha_fin, dtime.max).replace(tzinfo=timezone.utc)

    while True:
        params = {
            "limit_count": limit,
            "limit_offset": offset,
        }

        r = requests.get(
            f"{BASE_URL}/calls",
            headers=HEADERS,
            params=params,
            timeout=30
        )

        if r.status_code != 200:
            st.error(f"Error Ringover {r.status_code}")
            st.text(r.text[:3000])
            st.stop()

        data = r.json()
        batch = data.get("call_list", [])

        if not batch:
            break

        parar = False

        for call in batch:
            start_time = parse_fecha_ringover(call.get("start_time"))

            if start_time is None:
                continue

            if inicio_dt <= start_time <= fin_dt:
                llamadas.append(call)

            if start_time < inicio_dt:
                parar = True

        if parar:
            break

        if len(batch) < limit:
            break

        offset += limit
        time.sleep(0.55)

    return llamadas


def normalizar_llamada(call):
    user = call.get("user") or {}
    ivr = call.get("ivr") or {}

    user_id = user.get("user_id") or call.get("user_id")

    agente = user.get("concat_name")
    if not agente:
        agente = " ".join(
            str(x).strip()
            for x in [user.get("firstname"), user.get("lastname")]
            if x
        )

    if not agente:
        agente = f"Usuario {user_id}"

    return {
        "cdr_id": call.get("cdr_id"),
        "call_id": call.get("call_id"),
        "user_id": user_id,
        "Agente": agente,
        "email": user.get("email"),
        "ivr_id": ivr.get("ivr_id"),
        "ivr_name": ivr.get("name"),
        "direction": str(call.get("direction", "")).lower(),
        "is_answered": bool(call.get("is_answered")),
        "last_state": str(call.get("last_state", "")).upper(),
        "start_time": call.get("start_time"),
        "answered_time": call.get("answered_time"),
        "end_time": call.get("end_time"),
        "incall_duration_min": segundos_a_minutos(call.get("incall_duration")),
        "total_duration_min": segundos_a_minutos(call.get("total_duration")),
        "queue_duration_min": segundos_a_minutos(call.get("queue_duration")),
        "ringing_duration_min": segundos_a_minutos(call.get("ringing_duration")),
        "from_number": str(call.get("from_number", "")).strip(),
        "to_number": str(call.get("to_number", "")).strip(),
        "contact_number": str(call.get("contact_number", "")).strip(),
    }


def calcular_kpis(llamadas_raw, ivr_name):
    llamadas = [normalizar_llamada(c) for c in llamadas_raw]
    df = pd.DataFrame(llamadas)

    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    df_ventas = df[
        df["ivr_name"].fillna("").str.lower() == ivr_name.lower()
    ].copy()

    if df_ventas.empty:
        return pd.DataFrame(), df_ventas

    resultados = []

    for (user_id, agente), sub in df_ventas.groupby(["user_id", "Agente"], dropna=False):
        entrantes = sub[sub["direction"].isin(["in", "incoming", "inbound"])]
        salientes = sub[sub["direction"].isin(["out", "outgoing", "outbound"])]
        contestadas = sub[sub["is_answered"] == True]

        call_in = len(entrantes)
        call_out = len(salientes)
        contestadas_n = len(contestadas)

        time_in = entrantes["incall_duration_min"].sum()
        time_out = salientes["incall_duration_min"].sum()

        total_llamadas = call_in + call_out
        total_tiempo = time_in + time_out

        resultados.append({
            "Agente": agente,
            "user_id": user_id,
            "Horas": 0,
            "Call in": call_in,
            "Call out": call_out,
            "Conectadas": contestadas_n,
            "Contactab.": contestadas_n / call_out if call_out else 0,
            "Time in": time_in,
            "Time out": time_out,
            "Contestadas": contestadas_n,
            "Mid Calls": total_tiempo / total_llamadas if total_llamadas else 0,
            "Pólizas": 0,
            "Pólizas/h": 0,
            "Calls/h": 0,
            "Mid time in": time_in / call_in if call_in else 0,
            "Mid time out": time_out / call_out if call_out else 0,
            "Mid time": total_tiempo / total_llamadas if total_llamadas else 0,
        })

    kpis = pd.DataFrame(resultados).sort_values("Agente")
    return kpis, df_ventas


if st.button("Generar KPIs"):
    with st.spinner("Descargando llamadas de Ringover..."):
        llamadas_raw = get_calls_sin_fechas(fecha_inicio, fecha_fin)

    st.write("Llamadas descargadas en rango:", len(llamadas_raw))

    kpis, llamadas_ventas = calcular_kpis(llamadas_raw, ivr_name)

    st.subheader("KPIs Ventas")
    st.dataframe(kpis)

    st.subheader("Llamadas Ventas")
    st.dataframe(llamadas_ventas)

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        kpis.to_excel(writer, sheet_name="KPIs", index=False)
        llamadas_ventas.to_excel(writer, sheet_name="Llamadas Ventas", index=False)

    st.download_button(
        label="Descargar Excel",
        data=output.getvalue(),
        file_name="kpis_ringover_ventas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
