# pip install requests pandas openpyxl python-dotenv

import os
import time
import requests
import pandas as pd

API_KEY = os.getenv("RINGOVER_API_KEY")
# API_KEY = "TU_API_KEY"  # opción rápida para probar

BASE_URL = "https://public-api.ringover.com/v2"

if not API_KEY:
    raise ValueError("Falta API_KEY. Define RINGOVER_API_KEY o pon API_KEY = 'TU_API_KEY'.")

HEADERS = {
    "Authorization": API_KEY
}

def get_calls(fecha_inicio: str, fecha_fin: str):
    llamadas = []
    offset = 0
    limit = 100

    while True:
        params = {
            "limit_count": limit,
            "limit_offset": offset,
            "start_date": fecha_inicio,
            "end_date": fecha_fin,
        }

        r = requests.get(
            f"{BASE_URL}/calls",
            headers=HEADERS,
            params=params,
            timeout=30
        )

        print("URL:", r.url)
        print("STATUS:", r.status_code)

        r.raise_for_status()
        data = r.json()

        batch = (
            data.get("call_list")
            or data.get("list")
            or data.get("calls")
            or data.get("data")
            or []
        )

        if not batch:
            break

        llamadas.extend(batch)

        if len(batch) < limit:
            break

        offset += limit
        time.sleep(0.55)

    return llamadas

def segundos_a_minutos(valor):
    if valor is None:
        return 0
    return float(valor) / 60

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
        "from_number": call.get("from_number"),
        "to_number": call.get("to_number"),
        "contact_number": call.get("contact_number"),
    }

def calcular_kpis_ventas(
    fecha_inicio: str,
    fecha_fin: str,
    ivr_name: str = "Ventas",
    horas_por_agente: dict | None = None,
    polizas_por_agente: dict | None = None
):
    llamadas_raw = get_calls(fecha_inicio, fecha_fin)
    llamadas = [normalizar_llamada(c) for c in llamadas_raw]

    df = pd.DataFrame(llamadas)

    if df.empty:
        return pd.DataFrame(), df

    df_ventas = df[
        df["ivr_name"].fillna("").str.lower() == ivr_name.lower()
    ].copy()

    if df_ventas.empty:
        print(f"No hay llamadas para IVR/Centralita: {ivr_name}")
        return pd.DataFrame(), df

    resultados = []

    for (user_id, agente), sub in df_ventas.groupby(["user_id", "Agente"], dropna=False):
        entrantes = sub[sub["direction"].isin(["in", "incoming", "inbound"])]
        salientes = sub[sub["direction"].isin(["out", "outgoing", "outbound"])]

        contestadas = sub[sub["is_answered"] == True]

        call_in = len(entrantes)
        call_out = len(salientes)
        conectadas = len(contestadas)

        time_in = entrantes["incall_duration_min"].sum()
        time_out = salientes["incall_duration_min"].sum()

        total_llamadas = call_in + call_out
        total_tiempo = time_in + time_out

        horas = 0
        polizas = 0

        if horas_por_agente:
            horas = horas_por_agente.get(agente, 0)

        if polizas_por_agente:
            polizas = polizas_por_agente.get(agente, 0)

        resultados.append({
            "Agente": agente,
            "user_id": user_id,
            "Horas": horas,
            "Call in": call_in,
            "Call out": call_out,
            "Conectadas": conectadas,
            "Contactab.": conectadas / call_out if call_out else 0,
            "Time in": time_in,
            "Time out": time_out,
            "Contestadas": conectadas,
            "Mid Calls": total_tiempo / total_llamadas if total_llamadas else 0,
            "Pólizas": polizas,
            "Pólizas/h": polizas / horas if horas else 0,
            "Calls/h": total_llamadas / horas if horas else 0,
            "Mid time in": time_in / call_in if call_in else 0,
            "Mid time out": time_out / call_out if call_out else 0,
            "Mid time": total_tiempo / total_llamadas if total_llamadas else 0,
        })

    kpis = pd.DataFrame(resultados)
    kpis = kpis.sort_values("Agente")

    return kpis, df_ventas

if __name__ == "__main__":
    fecha_inicio = "2026-06-01"
    fecha_fin = "2026-06-30"

    horas_por_agente = {
        "Jesús Alemán": 155,
        "Isabel": 155,
        "Toñi": 105,
    }

    polizas_por_agente = {
        "Jesús Alemán": 34,
        "Isabel": 34,
        "Toñi": 11,
    }

    kpis, llamadas_ventas = calcular_kpis_ventas(
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        ivr_name="Ventas",
        horas_por_agente=horas_por_agente,
        polizas_por_agente=polizas_por_agente
    )

    with pd.ExcelWriter("kpis_ringover_ventas.xlsx", engine="openpyxl") as writer:
        kpis.to_excel(writer, sheet_name="KPIs", index=False)
        llamadas_ventas.to_excel(writer, sheet_name="Llamadas Ventas", index=False)

    print(kpis)
