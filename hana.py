import os
from dotenv import load_dotenv

load_dotenv()

HANA_HOST = os.getenv("HANA_HOST")
HANA_PORT = int(os.getenv("HANA_PORT", 443))
HANA_USER = os.getenv("HANA_USER")
HANA_PASSWORD = os.getenv("HANA_PASSWORD")


def get_connection():
    from hdbcli import dbapi
    conn = dbapi.connect(
        address=HANA_HOST,
        port=HANA_PORT,
        user=HANA_USER,
        password=HANA_PASSWORD,
        encrypt=True,
        sslValidateCertificate=False,
        connectTimeout=5000
    )
    return conn


def setup_tables():
    conn = get_connection()
    cursor = conn.cursor()

    for table, ddl in [
        ("SAP_LOGS", """
            CREATE TABLE SAP_LOGS (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                window_id VARCHAR(30),
                log_type VARCHAR(50),
                application VARCHAR(100),
                http_status_code INT,
                client_ip VARCHAR(50),
                llm_cost_usd DOUBLE,
                llm_response_time_ms DOUBLE,
                llm_provider VARCHAR(50),
                region VARCHAR(50),
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """),
        ("SAP_ALERTS", """
            CREATE TABLE SAP_ALERTS (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                timestamp_utc VARCHAR(50),
                alert_type VARCHAR(50),
                severity VARCHAR(10),
                message VARCHAR(500),
                status_code INT,
                window_start VARCHAR(50),
                response_ms DOUBLE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    ]:
        try:
            cursor.execute(ddl)
        except Exception as e:
            if "duplicate table name" in str(e).lower() or "table already exists" in str(e).lower():
                print(f"  Tabla {table} ya existe — OK")
            else:
                raise

    conn.commit()
    cursor.close()
    conn.close()
    print("Tablas SAP_LOGS y SAP_ALERTS listas.")


def insert_logs(df, window_id):
    conn = get_connection()
    cursor = conn.cursor()

    cols = {
        "log_type": "sap_function_log_type",
        "application": "sap_function_application",
        "http_status_code": "http_status_code",
        "client_ip": "client_ip",
        "llm_cost_usd": "llm_cost_usd",
        "llm_response_time_ms": "llm_response_time_ms",
        "llm_provider": "llm_provider",
        "region": "region"
    }

    rows = []
    for _, row in df.iterrows():
        rows.append((
            window_id,
            str(row.get(cols["log_type"], ""))[:50],
            str(row.get(cols["application"], ""))[:100],
            int(row[cols["http_status_code"]]) if str(row.get(cols["http_status_code"], "")).lstrip("-").isdigit() else None,
            str(row.get(cols["client_ip"], ""))[:50],
            float(row[cols["llm_cost_usd"]]) if str(row.get(cols["llm_cost_usd"], "")).replace(".", "").isdigit() else None,
            float(row[cols["llm_response_time_ms"]]) if str(row.get(cols["llm_response_time_ms"], "")).replace(".", "").isdigit() else None,
            str(row.get(cols["llm_provider"], ""))[:50],
            str(row.get(cols["region"], ""))[:50],
        ))

    cursor.executemany("""
        INSERT INTO SAP_LOGS
        (window_id, log_type, application, http_status_code, client_ip,
         llm_cost_usd, llm_response_time_ms, llm_provider, region)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, rows)

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  HANA: {len(rows)} registros insertados en SAP_LOGS.")


def insert_alert(timestamp_utc, alert_type, severity, message, status_code, window_start, response_ms):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO SAP_ALERTS
        (timestamp_utc, alert_type, severity, message, status_code, window_start, response_ms)
        VALUES (?,?,?,?,?,?,?)
    """, (timestamp_utc, alert_type, severity, message[:500], status_code, window_start, response_ms))

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  HANA: alerta insertada en SAP_ALERTS.")


if __name__ == "__main__":
    print("Probando conexión a SAP HANA Cloud...")
    try:
        conn = get_connection()
        print("Conexión exitosa.")
        conn.close()
        setup_tables()
    except Exception as e:
        print(f"Error: {e}")