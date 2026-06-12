import time
from io import BytesIO
from datetime import datetime, time as dtime, timezone
import unicodedata

import requests
import pandas as pd
import streamlit as st


DASHBOARD_URL = "https://api-eu.ringover.com/v4/aud/dashboard/stats/calls/global"
VENTAS_IVR_ID = 11851068

st.title("KPIs Ringover - Ventas")

token = st.text_input("Bearer token Ringover", type="password")
fecha_inicio = st.date_input("Fecha inicio")
fecha_fin = st.date_input("Fecha fin")

config_file = st.file_uploader("Subir config_horarios_simple.xlsx", type=["xlsx"])
manual_file = st.file_uploader("Subir plantilla_datos_mensuales.xlsx", type=["xlsx"])


def normalizar(texto):
    texto = str(texto).upper().strip()
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def fecha_inicio_z(fecha):
    return datetime.combine(fecha, dtime.min).replace(
        tzinfo=timezone.utc
    ).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def fecha_fin_z(fecha):
    return datetime.combine(fecha, dtime.max).replace(
        tzinfo=timezone.utc
    ).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def buscar_match_agente(agente, df_config):
    agente_norm = normalizar(agente)

    for _, row in df_config.iterrows():
        match = normalizar(row["agente_match"])
        if match and match in agente_norm:
            return row

    return None


def asignar_horario(agente, df_agentes_horario):
    row = buscar_match_agente(agente, df_agentes_horario)
    if row is None:
        return None
    return int(row["horario_id"])


def contar_dias_tipo(fecha_inicio, fecha_fin, horario_id):
    dias = pd.date_range(fecha_inicio, fecha_fin, freq="D")

    if horario_id in [1, 3, 4, 6, 7]:
        dias_a = sum(d.weekday() in [0, 1, 2, 3] for d in dias)
        dias_b = sum(d.weekday() == 4 for d in dias)

    elif horario_id == 2:
        dias_a = sum(d.weekday() in [0, 1, 2, 3, 4] for d in dias)
        dias_b = 0

    elif horario_id == 5:
        dias_a = sum(d.weekday() in [0, 1, 2, 3, 4, 5] for d in dias)
        dias_b = 0

    else:
        dias_a = 0
        dias_b = 0

    return dias_a, dias_b


def llamar_stats(token, fecha_inicio, fecha_fin, user_id=None):
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
        "users": [int(user_id)] if user_id else [],
        "start_date": fecha_inicio_z(fecha_inicio),
        "end_date": fecha_fin_z(fecha_fin),
    }

    r = requests.post(
        DASHBOARD_URL,
        headers=headers,
        json=payload,
        timeout=30,
    )

    if r.status_code != 200:
        st.error(f"Error Ringover {r.status_code}")
        st.text(r.text[:3000])
        st.stop()

    return r.json().get("data", {})


def get_valor(data, posibles_campos):
    for campo in posibles_campos:
        if campo in data and data[campo] is not None:
            return data[campo]
    return 0


def calcular_horas(agente, fecha_inicio, fecha_fin, df_horarios, df_agentes_horario, vacaciones_a, vacaciones_b):
    horario_id = asignar_horario(agente, df_agentes_horario)

    if horario_id is None:
        return 0, None, 0, 0

    horario = df_horarios[df_horarios["horario_id"] == horario_id]

    if horario.empty:
        return 0, horario_id, 0, 0

    horario = horario.iloc[0]

    dias_a_mes, dias_b_mes = contar_dias_tipo(fecha_inicio, fecha_fin, horario_id)

    dias_a = max(dias_a_mes - vacaciones_a, 0)
    dias_b = max(dias_b_mes - vacaciones_b, 0)

    horas = (
        dias_a * float(horario["horas_dia_a"])
        + dias_b * float(horario["horas_dia_b"])
    )

    return horas, horario_id, dias_a, dias_b


def calcular_kpis(token, fecha_inicio, fecha_fin, df_horarios, df_agentes_horario, df_manual):
    resultados = []

    for _, row in df_manual.iterrows():
        agente = row["agente_match"]
        user_id = row["user_id"]

        vacaciones_a = float(row.get("vacaciones_a", row.get("dias_a", 0)) or 0)
        vacaciones_b = float(row.get("vacaciones_b", row.get("dias_b", 0)) or 0)
        polizas = float(row.get("polizas", 0) or 0)

        data = llamar_stats(token, fecha_inicio, fecha_fin, user_id=user_id)

        call_in = get_valor(data, ["count_in"])
        call_out = get_valor(data, ["count_out"])
        conectadas = get_valor(data, ["count_out_answered"])
        contestadas = get_valor(data, ["count_in_answered"])
        perdidas = get_valor(data, ["count_in_missed"])

        time_in_sec = get_valor(data, [
            "duration_in",
            "duration_in_total",
            "total_duration_in",
            "sum_duration_in"
        ])

        time_out_sec = get_valor(data, [
            "duration_out",
            "duration_out_total",
            "total_duration_out",
            "sum_duration_out"
        ])

        time_in = time_in_sec / 60
        time_out = time_out_sec / 60

        total_llamadas = call_in + call_out
        total_tiempo = time_in + time_out

        horas, horario_id, dias_a, dias_b = calcular_horas(
            agente,
            fecha_inicio,
            fecha_fin,
            df_horarios,
            df_agentes_horario,
            vacaciones_a,
            vacaciones_b,
        )

        contactab = conectadas / call_out if call_out else 0
        mid_time = total_tiempo / total_llamadas if total_llamadas else 0
        indice_productividad = total_llamadas / horas if horas else 0
        indice_efectividad = polizas / horas if horas else 0

        resultados.append({
            "Agente": agente,
            "user_id": user_id,
            "horario_id": horario_id,
            "Vacaciones A": vacaciones_a,
            "Vacaciones B": vacaciones_b,
            "Días A": dias_a,
            "Días B": dias_b,
            "Horas": horas,
            "Call in": call_in,
            "Call out": call_out,
            "Conectadas": conectadas,
            "Contactab.": contactab,
            "Time in": time_in,
            "Time out": time_out,
            "Contestadas": contestadas,
            "Perdidas": perdidas,
            "Mid Calls": mid_time,
            "Pólizas": polizas,
            "Índice efectividad": indice_efectividad,
            "Índice productividad": indice_productividad,
            "Mid time": mid_time,
        })

        time.sleep(0.2)

    return pd.DataFrame(resultados)


if st.button("Generar KPIs"):
    if not token:
        st.error("Pega el Bearer token.")
        st.stop()

    if not config_file or not manual_file:
        st.error("Sube los dos Excel.")
        st.stop()

    df_horarios = pd.read_excel(config_file, sheet_name="Horarios")
    df_agentes_horario = pd.read_excel(config_file, sheet_name="AgentesHorario")
    df_manual = pd.read_excel(manual_file, sheet_name="DatosManuales")

    if "user_id" not in df_manual.columns:
        st.error("El Excel mensual debe tener una columna user_id.")
        st.stop()

    with st.spinner("Consultando estadísticas oficiales de Ringover..."):
        kpis = calcular_kpis(
            token,
            fecha_inicio,
            fecha_fin,
            df_horarios,
            df_agentes_horario,
            df_manual,
        )

    st.subheader("KPIs Ventas")
    st.dataframe(kpis)

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        kpis.to_excel(writer, sheet_name="KPIs", index=False)

    st.download_button(
        "Descargar Excel",
        data=output.getvalue(),
        file_name="kpis_ringover_ventas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
