import os
import time
import requests
import pandas as pd

API_KEY = os.getenv("RINGOVER_API_KEY")
BASE_URL = "https://public-api.ringover.com/v2"

HEADERS = {
    "Authorization": API_KEY
}

def get_json(endpoint, params=None):
    r = requests.get(
        f"{BASE_URL}{endpoint}",
        headers=HEADERS,
        params=params or {},
        timeout=30
    )
    r.raise_for_status()
    return r.json()

def buscar_grupo(nombre_grupo="Ventas"):
    data = get_json("/groups", {
        "limit_count": 1000,
        "limit_offset": 0
    })

    grupos = data.get("list") or data.get("groups") or data.get("data") or []

    print("Grupos encontrados:")
    for g in grupos:
        print(g.get("group_id") or g.get("id"), "-", g.get("name"))

    for grupo in grupos:
        if grupo.get("name", "").strip().lower() == nombre_grupo.strip().lower():
            return grupo

    raise ValueError(f"No he encontrado el grupo: {nombre_grupo}")

def obtener_agentes_del_grupo(nombre_grupo="Ventas"):
    grupo = buscar_grupo(nombre_grupo)

    group_id = grupo.get("group_id") or grupo.get("id")

    data = get_json(f"/groups/{group_id}")

    usuarios = data.get("users") or data.get("members") or []

    filas = []

    for u in usuarios:
        user_id = u.get("user_id") or u.get("id")

        nombre = " ".join(
            str(x).strip()
            for x in [u.get("firstname"), u.get("lastname")]
            if x
        )

        if not nombre:
            nombre = u.get("name") or u.get("email") or str(user_id)

        filas.append({
            "user_id": user_id,
            "name": nombre,
            "email": u.get("email"),
            "group_id": group_id,
            "group_name": data.get("name") or grupo.get("name")
        })

    return pd.DataFrame(filas).drop_duplicates(subset=["user_id"])

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

def calcular_kpis(fecha_inicio, fecha_fin, agentes_ventas):
    llamadas_raw = get_calls(fecha_inicio, fecha_fin)
    llamadas = [normalizar_llamada(c) for c in llamadas_raw]
    df = pd.DataFrame(llamadas)

    resultados = []

    for nombre, cfg in agentes_ventas.items():
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
        })

    return pd.DataFrame(resultados)

if __name__ == "__main__":
    df_agentes = obtener_agentes_del_grupo("Ventas")

    print("Agentes encontrados:")
    print(df_agentes)

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

    fecha_inicio = "2026-05-01"
    fecha_fin = "2026-05-31"

    kpis = calcular_kpis(fecha_inicio, fecha_fin, AGENTES_VENTAS)

    with pd.ExcelWriter("kpis_ringover_ventas.xlsx", engine="openpyxl") as writer:
        df_agentes.to_excel(writer, sheet_name="Agentes Ventas", index=False)
        kpis.to_excel(writer, sheet_name="KPIs", index=False)

    print(kpis)
