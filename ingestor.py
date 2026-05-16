import requests
import pandas as pd
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TOKEN   = os.getenv("SAP_TOKEN")
BASE    = os.getenv("SAP_BASE_URL")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def check_server():
    r = requests.get(f"{BASE}/health")
    print("Servidor:", r.json())


def get_info():
    r = requests.get(f"{BASE}/info", headers=HEADERS)
    info = r.json()
    print("Info ventana actual:", json.dumps(info, indent=2))
    return info


def fetch_logs():
    print("Obteniendo página 1...")
    r = requests.get(f"{BASE}/logs/current", headers=HEADERS, params={"page": 1})
    payload = r.json()

    total_pages = payload["total_pages"]
    total_records = payload["total_records"]
    window_start = payload["window_start"]
    window_end = payload["window_end"]

    print(f"Ventana: {window_start} → {window_end}")
    print(f"Total registros: {total_records} en {total_pages} páginas")

    print("\nRaw payload página 1:")
    print(json.dumps(payload, indent=2)[:1000])  # primeros 1000 chars

    all_records = payload["data"]

    for page in range(2, total_pages + 1):
        print(f"Obteniendo página {page}/{total_pages}...")
        r = requests.get(f"{BASE}/logs/current", headers=HEADERS, params={"page": page})
        all_records.extend(r.json()["data"])

    df = pd.DataFrame(all_records)
    print(f"\nDataFrame listo: {df.shape[0]} filas, {df.shape[1]} columnas")
    print("\nColumnas disponibles:")
    print(df.columns.tolist())
    print("\nTipos de log:")
    log_col = next((c for c in df.columns if "log_type" in c.lower()), None)
    if log_col:
        print(df[log_col].value_counts())
    else:
        print("(columna log_type no encontrada, revisa columnas arriba)")

    # Guardar localmente
    filename = f"logs_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
    df.to_csv(filename, index=False)
    print(f"\nGuardado en: {filename}")

    return df


def send_alert(message: str):
    if len(message) > 300:
        print("ERROR: mensaje excede 300 caracteres")
        return

    r = requests.post(
        f"{BASE}/alert",
        headers=HEADERS,
        json={"message": message}
    )
    print("Respuesta alerta:", r.json())


if __name__ == "__main__":
    check_server()
    get_info()
    df = fetch_logs()
    print("\nPrimeras filas:")
    print(df.head())
