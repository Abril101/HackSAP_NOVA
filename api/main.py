import os
import json
import smtplib
import pandas as pd
import requests as req
from datetime import datetime, timezone
from email.mime.text import MIMEText
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url=os.getenv("ENDPOINT"),
    api_key=os.getenv("API_KEY")
)

OPENAI_MODEL = os.getenv("DEPLOYMENT_NAME")

TOKEN   = os.getenv("SAP_TOKEN")
BASE    = os.getenv("SAP_BASE_URL")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# Paths para fallback CSV
ALERTS_PATH   = "data/alerts_log.csv"
BASELINE_PATH = "data/baseline_cache.json"

app = FastAPI(
    title="NOVA API",
    description="Sistema de Deteccion de Amenazas SAP - Equipo NOVA",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Modelos de request ────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str


# ── Conexión HANA ─────────────────────────────────────────────────

def get_hana_connection():
    """
    Retorna una conexión a SAP HANA Cloud usando hdbcli.
    Requiere en .env:
      HANA_HOST, HANA_PORT, HANA_USER, HANA_PASSWORD
    """
    try:
        from hdbcli import dbapi
        conn = dbapi.connect(
            address=os.getenv("HANA_HOST"),
            port=int(os.getenv("HANA_PORT", 443)),
            user=os.getenv("HANA_USER"),
            password=os.getenv("HANA_PASSWORD"),
            encrypt=True,
            sslValidateCertificate=False,
        )
        return conn
    except ImportError:
        raise RuntimeError("hdbcli no instalado. Ejecuta: pip install hdbcli")
    except Exception as e:
        raise RuntimeError(f"No se pudo conectar a HANA: {e}")


# ── Helpers ───────────────────────────────────────────────────────

def load_alerts() -> list[dict]:
    """
    Carga alertas desde SAP HANA (tabla SAP_ALERTS).
    Fallback a CSV si HANA no está disponible.
    Columnas esperadas en HANA:
      timestamp_utc, alert_type, severity, message,
      status_code, window_start, response_ms
    """
    # ── Intentar HANA primero ──
    try:
        conn   = get_hana_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp_utc, alert_type, severity, message,
                   status_code, window_start, response_ms
            FROM SAP_ALERTS
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        cols = [
            "timestamp_utc", "alert_type", "severity", "message",
            "status_code", "window_start", "response_ms"
        ]
        cursor.close()
        conn.close()
        return pd.DataFrame(rows, columns=cols).to_dict(orient="records")

    except Exception as hana_err:
        print(f"  [HANA] alerts fallback a CSV — {hana_err}")

    # ── Fallback CSV ──
    if not os.path.exists(ALERTS_PATH):
        return []
    try:
        df = pd.read_csv(ALERTS_PATH, on_bad_lines="skip")
        df = df.sort_values("timestamp_utc", ascending=False)
        return df.to_dict(orient="records")
    except Exception:
        return []


def load_logs(limit: int = 500, date_str: str = None) -> list[dict]:
    """
    Carga logs SAP desde HANA (tabla SAP_LOGS).
    Columnas esperadas en HANA:
      window_id, log_type, application, http_status_code,
      client_ip, llm_cost_usd, llm_response_time_ms, llm_provider, region
    Parámetros opcionales:
      limit     — máximo de registros a devolver
      date_str  — filtrar por fecha (ej: "20260504", se compara con window_id)
    """
    try:
        conn   = get_hana_connection()
        cursor = conn.cursor()

        where  = f"WHERE window_id LIKE '{date_str}%'" if date_str else ""
        cursor.execute(f"""
            SELECT window_id, log_type, application, http_status_code,
                   client_ip, llm_cost_usd, llm_response_time_ms, llm_provider, region
            FROM SAP_LOGS
            {where}
            ORDER BY window_id DESC
            LIMIT {limit}
        """)
        rows = cursor.fetchall()
        cols = [
            "_window", "sap_function_log_type", "sap_function_application",
            "http_status_code", "client_ip", "llm_cost_usd",
            "llm_response_time_ms", "llm_provider", "region"
        ]
        cursor.close()
        conn.close()
        return pd.DataFrame(rows, columns=cols).to_dict(orient="records")

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo cargar SAP_LOGS desde HANA: {e}"
        )


def get_sap_status() -> dict:
    """Estado del servidor SAP BTP (igual que antes)."""
    try:
        health = req.get(f"{BASE}/health", timeout=5).json()
        info   = req.get(f"{BASE}/info", headers=HEADERS, timeout=5).json()
        return {"server": health.get("status"), **info}
    except Exception as e:
        return {"server": "error", "detail": str(e)}


def send_email_alert(subject: str, body: str):
    """Envía correo vía SMTP cuando el pipeline falla."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    recipient = os.getenv("ALERT_EMAIL")

    if not all([smtp_user, smtp_pass, recipient]):
        print("  Email no configurado — faltan SMTP_USER, SMTP_PASSWORD o ALERT_EMAIL en .env")
        return False

    msg            = MIMEText(body)
    msg["Subject"] = subject
    msg["From"]    = smtp_user
    msg["To"]      = recipient

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        print(f"  Email enviado a {recipient}")
        return True
    except Exception as e:
        print(f"  Error enviando email: {e}")
        return False


# ── Endpoints ─────────────────────────────────────────────────────

@app.get("/")
def root():
    """Health check de la API NOVA."""
    return {
        "system":        "NOVA",
        "status":        "online",
        "version":       "2.0.0",
        "data_source":   "HANA Cloud (fallback CSV)",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "endpoints":     ["/alerts", "/logs", "/status", "/chat",
                          "/trigger", "/baseline", "/notify-pipeline-down"]
    }


@app.get("/alerts")
def get_alerts(
    limit:    int = Query(50,  ge=1,  le=1000, description="Máximo de alertas a devolver"),
    severity: str = Query(None, description="Filtrar por HIGH o MEDIUM"),
    date:     str = Query(None, description="Filtrar por fecha YYYYMMDD (compara window_start)"),
):
    """
    Devuelve el historial de alertas desde SAP HANA (tabla SAP_ALERTS).
    Fallback automático a CSV si HANA no está disponible.
    """
    alerts = load_alerts()

    if severity:
        alerts = [a for a in alerts if a.get("severity") == severity.upper()]

    if date:
        # Filtrar por window_start o timestamp_utc que contengan la fecha
        date_fmt = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        alerts = [
            a for a in alerts
            if (str(a.get("timestamp_utc", "")).startswith(date_fmt)
                or str(a.get("window_start", "")).startswith(date_fmt)
                or str(a.get("window_start", "")).startswith(date))
        ]

    return {
        "total":       len(alerts),
        "data_source": "hana",
        "alerts":      alerts[:limit]
    }


@app.get("/logs")
def get_logs(
    limit:    int = Query(500, ge=1, le=5000, description="Máximo de registros"),
    date:     str = Query(None, description="Filtrar por fecha YYYYMMDD (se compara con window_id)"),
    log_type: str = Query(None, description="Filtrar por tipo de log (ej: LLM_ERROR)"),
    app_name: str = Query(None, description="Filtrar por aplicación SAP"),
):
    """
    Devuelve logs SAP desde HANA (tabla SAP_LOGS).
    Misma query que usa el dashboard en load_from_hana().
    """
    records = load_logs(limit=limit, date_str=date)

    if log_type:
        records = [r for r in records if r.get("sap_function_log_type") == log_type.upper()]

    if app_name:
        records = [
            r for r in records
            if app_name.lower() in str(r.get("sap_function_application", "")).lower()
        ]

    return {
        "total":       len(records),
        "data_source": "hana",
        "logs":        records
    }


@app.get("/status")
def get_status():
    """
    Estado actual del sistema: servidor SAP, ventana activa,
    número de alertas enviadas por severidad, última alerta.
    Los conteos de alertas vienen de HANA (tabla SAP_ALERTS).
    """
    sap    = get_sap_status()
    alerts = load_alerts()

    last_alert = alerts[0] if alerts else None

    return {
        "sap_server":    sap.get("server"),
        "window_start":  sap.get("window_start"),
        "window_end":    sap.get("window_end"),
        "total_records": sap.get("total_records"),
        "total_alerts":  len(alerts),
        "high_alerts":   sum(1 for a in alerts if a.get("severity") == "HIGH"),
        "medium_alerts": sum(1 for a in alerts if a.get("severity") == "MEDIUM"),
        "last_alert":    last_alert,
        "data_source":   "hana",
        "timestamp_utc": datetime.now(timezone.utc).isoformat()
    }


@app.get("/baseline")
def get_baseline():
    """Devuelve el baseline actual del modelo (umbrales calculados)."""
    if not os.path.exists(BASELINE_PATH):
        raise HTTPException(
            status_code=404,
            detail="Baseline no encontrado. Corre el pipeline primero."
        )
    with open(BASELINE_PATH) as f:
        data = json.load(f)
    return data


@app.post("/chat")
def chat(body: ChatRequest):
    """
    Chatbot que responde preguntas sobre las alertas en lenguaje natural.
    Usa las alertas de HANA como contexto.
    """
    alerts = load_alerts()

    if not alerts:
        context = "No hay alertas registradas aún en el sistema."
    else:
        lines = []
        for a in alerts[:20]:
            lines.append(
                f"- [{a.get('severity','?')}] {a.get('alert_type','?')} "
                f"| {str(a.get('timestamp_utc','?'))[:19]} "
                f"| {str(a.get('message',''))[:120]}"
            )
        context = "\n".join(lines)

    sap_status    = get_sap_status()
    ventana_actual = sap_status.get("window_start", "desconocida")

    prompt = f"""Eres el asistente del equipo NOVA, un sistema de detección de amenazas
en tiempo real para logs de SAP.

Contexto del sistema:
- Fuente de datos: SAP HANA Cloud (tabla SAP_ALERTS)
- Ventana activa: {ventana_actual}
- Total de alertas enviadas: {len(alerts)}
- Últimas alertas:
{context}

El sistema tiene 5 capas de detección:
1. Reglas con umbrales dinámicos (MAD 3-sigma)
2. Z-score robusto histórico
3. Detección por aplicación SAP
4. Isolation Forest
5. One-Class SVM (novelty detection)

Pregunta del usuario: {body.question}

Responde en español, de forma clara y concisa. Si la pregunta es sobre una alerta
específica, explica qué detectó y por qué se disparó. Si no tienes información
suficiente, dilo claramente."""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        answer = response.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en Gemini API: {e}")

    return {
        "question": body.question,
        "answer": answer,
        "context_alerts": len(alerts),
        "timestamp_utc": datetime.now(timezone.utc).isoformat()
    }


@app.post("/trigger")
def trigger_detection():
    """
    Corre el detector manualmente sobre la ventana actual.
    """
    try:
        from detector import run_detection
        import glob

        files = sorted(glob.glob("data/logs_*.csv"), reverse=True)
        if not files:
            raise HTTPException(
                status_code=404,
                detail="No hay CSVs. Corre pipeline.py primero."
            )

        df     = pd.read_csv(files[0])
        window = files[0].replace("data/logs_", "").replace(".csv", "")

        run_detection(df, window_start=window)

        return {
            "status":           "detection complete",
            "window":           window,
            "records_analyzed": len(df),
            "timestamp_utc":    datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/notify-pipeline-down")
def notify_pipeline_down():
    """
    Notifica por email cuando el pipeline deja de hacer llamadas.
    Se llama desde un cron job o monitor externo.
    """
    sent = send_email_alert(
        subject="NOVA ALERTA: Pipeline caído",
        body=(
            f"El pipeline de NOVA no ha hecho llamadas a la API de SAP "
            f"en los últimos 30 minutos.\n\n"
            f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
            f"Acción requerida: revisar Railway/BTP y reiniciar el worker si es necesario."
        )
    )
    return {
        "email_sent":    sent,
        "timestamp_utc": datetime.now(timezone.utc).isoformat()
    }
