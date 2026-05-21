import requests
import pandas as pd
import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from detector import run_detection
from hana import insert_logs, setup_tables
from hdbcli import dbapi

HANA_ENABLED = True

load_dotenv()

TOKEN   = os.getenv("SAP_TOKEN")
BASE    = os.getenv("SAP_BASE_URL")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

os.makedirs("data", exist_ok=True)
analyzed_windows = set()


def get_window_minute():
    """Minuto actual dentro de la ventana de 30 min (0-29)."""
    return datetime.now(timezone.utc).minute % 30


def fetch_info():
    try:
        r = requests.get(f"{BASE}/info", headers=HEADERS, timeout=10)
        return r.json()
    except Exception as e:
        print(f"  Error en /info: {e}")
        return None


def fetch_and_save():
    now_str = datetime.utcnow().strftime("%Y%m%d_%H%M")
    print(f"\n[{datetime.utcnow().strftime('%H:%M:%S')} UTC] Ingesta...")

    info = fetch_info()
    if not info or info.get("total_records", 0) == 0:
        return False, None, None, None

    total_pages   = info["total_pages"]
    total_records = info["total_records"]
    window_start  = info["window_start"]
    print(f"  Ventana: {window_start} | Registros: {total_records}")

    all_records = []
    for page in range(1, total_pages + 1):
        try:
            r = requests.get(f"{BASE}/logs/current", headers=HEADERS,
                             params={"page": page}, timeout=30)
            all_records.extend(r.json().get("data", []))
        except Exception as e:
            print(f"  Error página {page}: {e}")

    if not all_records:
        return False, None, None, None

    fetch_time = datetime.now(timezone.utc)
    df = pd.DataFrame(all_records)
    window_str = pd.to_datetime(window_start).strftime("%Y%m%d_%H%M")
    filename = f"data/logs_{window_str}.csv"
    df.to_csv(filename, index=False)
    print(f"  Guardado: {filename} ({len(df)} filas)")
    if "sap_function_log_type" in df.columns:
        print(f"  Tipos:\n{df['sap_function_log_type'].value_counts().to_string()}")

    if HANA_ENABLED:
        try:
            insert_logs(df, now_str)
        except Exception as e:
            print(f"  HANA insert_logs error: {e}")

    return True, info["window_start"], df, fetch_time


def smart_poll_mode():
    """Polling cada 60s — detecta nuevas ventanas en cuanto aparecen."""
    print("\n MODO POLLING INTELIGENTE — poll cada 60s")
    print("=" * 60)

    while True:
        try:
            current_minute = get_window_minute()
            now_str = datetime.utcnow().strftime("%H:%M:%S")

            info = fetch_info()

            if info and info.get("total_records", 0) > 0:
                window_start = info["window_start"]

                if window_start not in analyzed_windows:
                    success, ws, df, fetch_time = fetch_and_save()
                    if success:
                        analyzed_windows.add(ws)
                        run_detection(df, window_start=ws, fetch_time=fetch_time)
                else:
                    print(f"  [{now_str} UTC] Ventana {window_start[11:16]} ya analizada — min {current_minute}/30")
            else:
                print(f"  [{now_str} UTC] Sin datos — min {current_minute}/30")

        except Exception as e:
            print(f"  [ERROR] Excepcion en loop principal: {e}. Reintentando en 30s...")
            time.sleep(30)
            continue

        time.sleep(60)


if __name__ == "__main__":
    print("Pipeline NOVA iniciado. Ctrl+C para detener.\n")

    try:
        health = requests.get(f"{BASE}/health", timeout=10).json()
        print(f"Servidor: {health}")
    except Exception as e:
        print(f"No se puede conectar al servidor: {e}")
        exit(1)

    smart_poll_mode()
