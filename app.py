# pip install requests pandas openpyxl python-dotenv

import os
import time
import requests
import pandas as pd
from datetime import date

API_KEY = os.getenv("RINGOVER_API_KEY")
BASE_URL = "https://public-api.ringover.com/v2"

HEADERS = {
    "Authorization": API_KEY
}

df_agentes = obtener_agentes_del_grupo("Ventas")

AGENTES_VENTAS = {
    row["name"]: {
        "user_id": row["user_id"],
        "dias_a": 0,
        "dias_b": 0,
        "horas": 0,
        "polizas": 0
    }
    for _, row in df_agentes.iterrows()
}

def get_calls(fecha_inicio: str, fecha_fin: str):
    """
    Descarga llamadas entre dos fechas.
    Formato esperado: YYYY-MM-DD.
    Ajusta los nombres de los filtros de fecha si tu endpoint Ringover los llama distinto.
    """
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

        response = requests.get(
            f"{BASE_URL}/calls",
            headers=HEADERS,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        batch = data.get("list") or data.get("calls") or data.get("data") or []

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

    user_id = (
        call.get("user_id")
        or call.get("owner_user_id")
        or user.get("user_id")
        or user.get("id")
    )

    direccion = str(call.get("direction", "")).lower()
    estado = str(call.get("status", "")).upper()

    duracion_seg = (
        call.get("duration")
        or call.get("call_duration")
        or call.get("total_duration")
        or 0
    )

    return {
        "user_id": user_id,
        "direction": direccion,
        "status": estado,
        "duration_min": segundos_a_minutos(duracion_seg),
    }

def calcular_kpis(fecha_inicio, fecha_fin):
    llamadas_raw = get_calls(fecha_inicio, fecha_fin)
    llamadas = [normalizar_llamada(c) for c in llamadas_raw]
    df = pd.DataFrame(llamadas)

    resultados = []

    for nombre, cfg in AGENTES_VENTAS.items():
        user_id = cfg["user_id"]
        sub = df[df["user_id"] == user_id] if not df.empty else pd.DataFrame()

        entrantes = sub[sub["direction"].isin(["in", "incoming", "inbound"])]
        salientes = sub[sub["direction"].isin(["out", "outgoing", "outbound"])]

        contestadas = sub[sub["status"].isin([
            "ANSWERED",
            "CALL_ANSWERED",
            "COMPLETED"
        ])]

        llamadas_in = len(entrantes)
        llamadas_out = len(salientes)
        conectadas = len(contestadas)

        tiempo_in = entrantes["duration_min"].sum() if not entrantes.empty else 0
        tiempo_out = salientes["duration_min"].sum() if not salientes.empty else 0

        horas = cfg["horas"]
        polizas = cfg["polizas"]

        total_llamadas = llamadas_in + llamadas_out
        total_tiempo = tiempo_in + tiempo_out

        resultados.append({
            "Agente": nombre,
            "Días A": cfg["dias_a"],
            "Días B": cfg["dias_b"],
            "Horas": horas,
            "Call in": llamadas_in,
            "Call out": llamadas_out,
            "Conectadas": conectadas,
            "Contactab.": conectadas / llamadas_out if llamadas_out else 0,
            "Time in": tiempo_in,
            "Time out": tiempo_out,
            "Contestadas": conectadas,
            "Mid Calls": total_tiempo / total_llamadas if total_llamadas else 0,
            "Pólizas": polizas,
            "Pólizas/h": polizas / horas if horas else 0,
            "Calls/h": total_llamadas / horas if horas else 0,
            "Mid time in": tiempo_in / llamadas_in if llamadas_in else 0,
            "Mid time out": tiempo_out / llamadas_out if llamadas_out else 0,
            "Mid time": total_tiempo / total_llamadas if total_llamadas else 0,
        })

    return pd.DataFrame(resultados)

def calcular_variable(valor_w4, tramos):
    """
    Equivale a:
    =SI(W4<W29;"No variable"; SI(W4<W28;85%; ... ;170%))
    tramos debe ir de menor a mayor.
    """
    if valor_w4 < tramos["W29"]:
        return "No variable"
    if valor_w4 < tramos["W28"]:
        return "85%"
    if valor_w4 < tramos["W27"]:
        return "100%"
    if valor_w4 < tramos["W26"]:
        return "110%"
    if valor_w4 < tramos["W25"]:
        return "120%"
    if valor_w4 < tramos["W24"]:
        return "130%"
    if valor_w4 < tramos["W23"]:
        return "140%"
    if valor_w4 < tramos["W22"]:
        return "150%"
    if valor_w4 < tramos["W21"]:
        return "160%"
    return "170%"

if __name__ == "__main__":
    fecha_inicio = "2026-05-01"
    fecha_fin = "2026-05-31"

    kpis = calcular_kpis(fecha_inicio, fecha_fin)

    with pd.ExcelWriter("kpis_ringover_ventas.xlsx", engine="openpyxl") as writer:
        kpis.to_excel(writer, sheet_name="KPIs", index=False)

    print(kpis)
