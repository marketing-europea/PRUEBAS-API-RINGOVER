# pip install requests pandas openpyxl python-dotenv

import os
import time
import requests
import pandas as pd

API_KEY = "9100d3646e618b7526417ada74853f620bcfa288"

# Para probar rápido, puedes ponerla directa:
# API_KEY = "TU_API_KEY"

BASE_URL = "https://public-api.ringover.com/v2"

if not API_KEY:
    raise ValueError("No tienes API_KEY. Define RINGOVER_API_KEY o pon API_KEY = 'TU_API_KEY'.")

HEADERS = {
    "Authorization": API_KEY
}

def get_json(endpoint, params=None, fallar=True):
    url = f"{BASE_URL}{endpoint}"

    r = requests.get(
        url,
        headers=HEADERS,
        params=params or {},
        timeout=30
    )

    print("URL:", r.url)
    print("STATUS:", r.status_code)

    if r.status_code >= 400:
        print("RESPUESTA ERROR:", r.text[:2000])
        if fallar:
            r.raise_for_status()
        return None

    return r.json()

def obtener_agentes_desde_groups(nombre_grupo="Ventas"):
    data = get_json("/groups", {
        "limit_count": 1000,
        "limit_offset": 0
    }, fallar=False)

    if not data:
        return pd.DataFrame()

    grupos = data.get("list") or data.get("groups") or data.get("data") or []

    print("Grupos encontrados:")
    for g in grupos:
        print(g.get("group_id") or g.get("id"), "-", g.get("name"))

    grupo = None

    for g in grupos:
        if str(g.get("name", "")).strip().lower() == nombre_grupo.strip().lower():
            grupo = g
            break

    if not grupo:
        print(f"No se encontró el grupo {nombre_grupo}.")
        return pd.DataFrame()

    group_id = grupo.get("group_id") or grupo.get("id")

    detalle = get_json(f"/groups/{group_id}", fallar=False)

    if not detalle:
        return pd.DataFrame()

    usuarios = detalle.get("users") or detalle.get("members") or []

    filas = []

    for u in usuarios:
        user_id = u.get("user_id") or u.get("id")

        nombre = " ".join(
            str(x).strip()
            for x in [u.get("firstname"), u.get("lastname")]
            if x
        )

        if not nombre:
            nombre = u.get("name") or u.get("email") or f"Usuario {user_id}"

        filas.append({
            "user_id": user_id,
            "name": nombre,
            "email": u.get("email"),
            "group_id": group_id,
            "group_name": grupo.get("name")
        })

    return pd.DataFrame(filas).drop_duplicates(subset=["user_id"])

def obtener_agentes_desde_teams():
    data = get_json("/teams", fallar=True)

    print("Claves de /teams:", list(data.keys()))

    filas = []

    # Caso bueno: /teams trae users
    users = data.get("users") or data.get("members") or []

    for u in users:
        user_id = u.get("user_id") or u.get("id")

        nombre = " ".join(
            str(x).strip()
            for x in [u.get("firstname"), u.get("lastname")]
            if x
        )

        if not nombre:
            nombre = u.get("name") or u.get("email") or f"Usuario {user_id}"

        filas.append({
            "user_id": user_id,
            "name": nombre,
            "email": u.get("email"),
            "origen": "teams_users"
        })

    # Caso alternativo: solo trae numbers, sin nombres
    if not filas:
        numbers = data.get("numbers", [])

        for n in numbers:
            user_id = n.get("user_id")

            if user_id is not None:
                telefono = n.get("format", {}).get("international")

                filas.append({
                    "user_id": user_id,
                    "name": n.get("label") or f"Usuario {user_id}",
                    "email": None,
                    "telefono": telefono,
                    "origen": "teams_numbers"
                })

    return pd.DataFrame(filas).drop_duplicates(subset=["user_id"])

def obtener_agentes_ventas(nombre_grupo="Ventas"):
    df = obtener_agentes_desde_groups(nombre_grupo)

    if not df.empty:
        print("Agentes obtenidos desde /groups")
        return df

    print("No se pudo usar /groups. Probando /teams...")
    df = obtener_agentes_desde_teams()

    if df.empty:
        raise ValueError("No se han encontrado usuarios ni en /groups ni en /teams.")

    return df

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

        print("CALLS STATUS:", response.status_code)

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

        if sub.empty:
            llamadas_in = 0
            llamadas_out = 0
            conectadas = 0
            tiempo_in = 0
            tiempo_out = 0
        else:
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

            tiempo_in = entrantes["duration_min"].sum()
            tiempo_out = salientes["duration_min"].sum()

        horas = cfg["horas"]
        polizas = cfg["polizas"]

        total_llamadas = llamadas_in + llamadas_out
        total_tiempo = tiempo_in + tiempo_out

        resultados.append({
            "Agente": nombre,
            "user_id": user_id,
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
    fecha_inicio = "2026-05-01"
    fecha_fin = "2026-05-31"

    df_agentes = obtener_agentes_ventas("Ventas")

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

    kpis = calcular_kpis(fecha_inicio, fecha_fin, AGENTES_VENTAS)

    with pd.ExcelWriter("kpis_ringover_ventas.xlsx", engine="openpyxl") as writer:
        df_agentes.to_excel(writer, sheet_name="Agentes Ventas", index=False)
        kpis.to_excel(writer, sheet_name="KPIs", index=False)

    print(kpis)
