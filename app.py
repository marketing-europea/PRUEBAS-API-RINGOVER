import time
from io import BytesIO
from datetime import datetime, time as dtime, timezone
import unicodedata

import requests
import pandas as pd
import streamlit as st


API_KEY = "9100d3646e618b7526417ada74853f620bcfa288"
BASE_URL = "https://public-api.ringover.com/v2"
HEADERS = {"Authorization": API_KEY}

st.title("KPIs Ringover - Ventas")

fecha_inicio = st.date_input("Fecha inicio")
fecha_fin = st.date_input("Fecha fin")
ivr_name = st.text_input("Centralita / IVR", value="Ventas")

config_file = st.file_uploader("Subir config_horarios_ringover.xlsx", type=["xlsx"])
manual_file = st.file_uploader("Subir plantilla_datos_manuales_ringover.xlsx", type=["xlsx"])


def normalizar(texto):
    texto = str(texto).upper().strip()
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def segundos_a_minutos(valor):
    return 0 if valor is None else float(valor) / 60


def parse_fecha_ringover(valor):
    if not valor:
        return None
    return datetime.fromisoformat(valor.replace("Z", "+00:00"))


def contar_dias_periodo(fecha_inicio, fecha_fin):
    dias = pd.date_range(fecha_inicio, fecha_fin, freq="D")
    return {
        "lun_jue": sum(d.weekday() in [0, 1, 2, 3] for d in dias),
        "viernes": sum(d.weekday() == 4 for d in dias),
        "sabado": sum(d.weekday() == 5 for d in dias),
    }


def get_calls(fecha_inicio, fecha_fin):
    llamadas = []
    offset = 0
    limit = 100

    inicio_dt = datetime.combine(fecha_inicio, dtime.min).replace(tzinfo=timezone.utc)
    fin_dt = datetime.combine(fecha_fin, dtime.max).replace(tzinfo=timezone.utc)

    while True:
        r = requests.get(
            f"{BASE_URL}/calls",
            headers=HEADERS,
            params={"limit_count": limit, "limit_offset": offset},
            timeout=30
        )

        if r.status_code != 200:
            st.error(f"Error Ringover {r.status_code}")
            st.text(r.text[:3000])
            st.stop()

        batch = r.json().get("call_list", [])

        if not batch:
            break

        parar = False

        for call in batch:
            start_time = parse_fecha_ringover(call.get("start_time"))

            if start_time and inicio_dt <= start_time <= fin_dt:
                llamadas.append(call)

            if start_time and start_time < inicio_dt:
                parar = True

        if parar or len(batch) < limit:
            break

        offset += limit
        time.sleep(0.55)

    return llamadas


def normalizar_llamada(call):
    user = call.get("user") or {}
    ivr = call.get("ivr") or {}

    user_id = user.get("user_id") or call.get("user_id")
    agente = user.get("concat_name") or " ".join(
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
        "incall_duration_min": segundos_a_minutos(call.get("incall_duration")),
        "total_duration_min": segundos_a_minutos(call.get("total_duration")),
        "from_number": str(call.get("from_number", "")).strip(),
        "to_number": str(call.get("to_number", "")).strip(),
        "contact_number": str(call.get("contact_number", "")).strip(),
    }


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


def obtener_manual(agente, df_manual):
    row = buscar_match_agente(agente, df_manual)

    if row is None:
        return {"dias_a": 0, "dias_b": 0, "polizas": 0}

    return {
        "dias_a": float(row.get("dias_a", 0) or 0),
        "dias_b": float(row.get("dias_b", 0) or 0),
        "polizas": float(row.get("polizas", 0) or 0),
    }


def calcular_horas(agente, fecha_inicio, fecha_fin, df_horarios, df_agentes_horario, df_manual):
    horario_id = asignar_horario(agente, df_agentes_horario)

    if horario_id is None:
        return 0, None, 0, 0

    horario = df_horarios[df_horarios["horario_id"] == horario_id].iloc[0]
    manual = obtener_manual(agente, df_manual)
    dias = contar_dias_periodo(fecha_inicio, fecha_fin)

    horas_teoricas = (
        dias["lun_jue"] * float(horario["horas_lun_jue"])
        + dias["viernes"] * float(horario["horas_viernes"])
        + dias["sabado"] * float(horario["horas_sabado"])
    )

    horas_vacaciones = (
        manual["dias_a"] * float(horario["horas_dia_a"])
        + manual["dias_b"] * float(horario["horas_dia_b"])
    )

    horas = max(horas_teoricas - horas_vacaciones, 0)

    return horas, horario_id, manual["dias_a"], manual["dias_b"]


def calcular_kpis(llamadas_raw, ivr_name, fecha_inicio, fecha_fin, df_horarios, df_agentes_horario, df_manual):
    df = pd.DataFrame([normalizar_llamada(c) for c in llamadas_raw])

    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    df_ventas = df[df["ivr_name"].fillna("").str.lower() == ivr_name.lower()].copy()

    resultados = []

    for (user_id, agente), sub in df_ventas.groupby(["user_id", "Agente"], dropna=False):
    entrantes = sub[sub["direction"].isin(["in", "incoming", "inbound"])]
    salientes = sub[sub["direction"].isin(["out", "outgoing", "outbound"])]

    salientes_conectadas = salientes[salientes["is_answered"] == True]
    contestadas = sub[sub["is_answered"] == True]

    call_in = len(entrantes)
    call_out = len(salientes)

    conectadas = len(salientes_conectadas)
    contestadas_n = len(contestadas)

    # IMPORTANTE: usar duración total para cuadrar con Ringover
    time_in = entrantes["total_duration_min"].sum()
    time_out = salientes["total_duration_min"].sum()

    total_llamadas = call_in + call_out
    total_tiempo = time_in + time_out

    horas, horario_id, dias_a, dias_b = calcular_horas(
        agente, fecha_inicio, fecha_fin, df_horarios, df_agentes_horario, df_manual
    )

    manual = obtener_manual(agente, df_manual)
    polizas = manual["polizas"]

    resultados.append({
        "Agente": agente,
        "user_id": user_id,
        "horario_id": horario_id,
        "Días A": dias_a,
        "Días B": dias_b,
        "Horas": horas,
        "Call in": call_in,
        "Call out": call_out,
        "Conectadas": conectadas,
        "Contactab.": conectadas / call_out if call_out else 0,
        "Time in": time_in,
        "Time out": time_out,
        "Contestadas": contestadas_n,
        "Mid Calls": total_tiempo / total_llamadas if total_llamadas else 0,
        "Pólizas": polizas,
        "Pólizas/h": polizas / horas if horas else 0,
        "Calls/h": total_llamadas / horas if horas else 0,
    })

    return pd.DataFrame(resultados).sort_values("Agente"), df_ventas


if st.button("Generar KPIs"):
    if not config_file or not manual_file:
        st.error("Sube los dos Excel antes de generar KPIs.")
        st.stop()

    df_horarios = pd.read_excel(config_file, sheet_name="Horarios")
    df_agentes_horario = pd.read_excel(config_file, sheet_name="AgentesHorario")
    df_manual = pd.read_excel(manual_file, sheet_name="DatosManuales")

    with st.spinner("Descargando llamadas de Ringover..."):
        llamadas_raw = get_calls(fecha_inicio, fecha_fin)

    kpis, llamadas_ventas = calcular_kpis(
        llamadas_raw,
        ivr_name,
        fecha_inicio,
        fecha_fin,
        df_horarios,
        df_agentes_horario,
        df_manual
    )

    st.subheader("KPIs Ventas")
    st.dataframe(kpis)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        kpis.to_excel(writer, sheet_name="KPIs", index=False)
        llamadas_ventas.to_excel(writer, sheet_name="Llamadas Ventas", index=False)

    st.download_button(
        "Descargar Excel",
        data=output.getvalue(),
        file_name="kpis_ringover_ventas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
