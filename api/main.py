import os
import json
import smtplib
import pandas as pd
import requests as req
from datetime import datetime, timezone
from email.mime.text import MIMEText
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from google.genai.types import HttpOptions
from typer import prompt
from openai import OpenAI

load_dotenv()

#gemini_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
#gemini_client = genai.Client(http_options=HttpOptions(api_version="v1"))
#GEMINI_MODEL = os.getenv("GEMINI_MODEL")

client = OpenAI(
    base_url=os.getenv("ENDPOINT"),
    api_key=os.getenv("API_KEY")
)
OPENAI_MODEL = os.getenv("DEPLOYMENT_NAME")

TOKEN   = os.getenv("SAP_TOKEN")
BASE    = os.getenv("SAP_BASE_URL")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

ALERTS_PATH  = "data/alerts_log.csv"
BASELINE_PATH = "data/baseline_cache.json"

app = FastAPI(
    title="NOVA API",
    description="Sistema de Deteccion de Amenazas SAP - Equipo NOVA",
    version="1.0.0"
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


# ── Helpers ───────────────────────────────────────────────────────

def load_alerts() -> list[dict]:
    if not os.path.exists(ALERTS_PATH):
        return []
    try:
        df = pd.read_csv(ALERTS_PATH, on_bad_lines="skip")
        df = df.sort_values("timestamp_utc", ascending=False)
        return df.to_dict(orient="records")
    except Exception:
        return []


def get_sap_status() -> dict:
    try:
        health = req.get(f"{BASE}/health", timeout=5).json()
        info   = req.get(f"{BASE}/info", headers=HEADERS, timeout=5).json()
        return {"server": health.get("status"), **info}
    except Exception as e:
        return {"server": "error", "detail": str(e)}


def send_email_alert(subject: str, body: str):
    """Envia correo via SMTP cuando el pipeline falla."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    recipient = os.getenv("ALERT_EMAIL")

    if not all([smtp_user, smtp_pass, recipient]):
        print("  Email no configurado — faltan SMTP_USER, SMTP_PASSWORD o ALERT_EMAIL en .env")
        return False

    msg = MIMEText(body)
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
        "system": "NOVA",
        "status": "online",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "endpoints": ["/alerts", "/status", "/chat", "/trigger", "/baseline"]
    }


@app.get("/alerts")
def get_alerts(limit: int = 50, severity: str = None):
    """
    Devuelve el historial de alertas enviadas.
    Parametros opcionales:
      - limit: cuantas alertas devolver (default 50)
      - severity: filtrar por HIGH o MEDIUM
    """
    alerts = load_alerts()

    if severity:
        alerts = [a for a in alerts if a.get("severity") == severity.upper()]

    return {
        "total": len(alerts),
        "alerts": alerts[:limit]
    }


@app.get("/status")
def get_status():
    """
    Estado actual del sistema: servidor SAP, ventana activa, 
    numero de alertas enviadas, ultima alerta.
    """
    sap = get_sap_status()
    alerts = load_alerts()

    last_alert = alerts[0] if alerts else None

    return {
        "sap_server":     sap.get("server"),
        "window_start":   sap.get("window_start"),
        "window_end":     sap.get("window_end"),
        "total_records":  sap.get("total_records"),
        "total_alerts":   len(alerts),
        "high_alerts":    sum(1 for a in alerts if a.get("severity") == "HIGH"),
        "medium_alerts":  sum(1 for a in alerts if a.get("severity") == "MEDIUM"),
        "last_alert":     last_alert,
        "timestamp_utc":  datetime.now(timezone.utc).isoformat()
    }


@app.get("/baseline")
def get_baseline():
    """Devuelve el baseline actual del modelo (umbrales calculados)."""
    if not os.path.exists(BASELINE_PATH):
        raise HTTPException(status_code=404, detail="Baseline no encontrado. Corre el pipeline primero.")
    with open(BASELINE_PATH) as f:
        data = json.load(f)
    return data


@app.post("/chat")
def chat(body: ChatRequest):
    """
    Chatbot que responde preguntas sobre las alertas en lenguaje natural.
    Usa el historial de alertas como contexto.

    Ejemplo de pregunta: "que paso esta noche?" o "por que se disparo la alerta de LLM?"
    """
    alerts = load_alerts()

    if not alerts:
        context = "No hay alertas registradas aun en el sistema."
    else:
        lines = []
        for a in alerts[:20]:
            lines.append(
                f"- [{a.get('severity','?')}] {a.get('alert_type','?')} "
                f"| {a.get('timestamp_utc','?')[:19]} "
                f"| {a.get('message','')[:120]}"
            )
        context = "\n".join(lines)

    sap_status = get_sap_status()
    ventana_actual = sap_status.get("window_start", "desconocida")

    prompt = f"""Eres el asistente del equipo NOVA, un sistema de deteccion de amenazas en tiempo real para logs de SAP.

Contexto del sistema:
- Ventana activa: {ventana_actual}
- Total de alertas enviadas: {len(alerts)}
- Ultimas alertas:
{context}

El sistema tiene 5 capas de deteccion:
1. Reglas con umbrales dinamicos (MAD 3-sigma)
2. Z-score robusto historico
3. Deteccion por aplicacion SAP
4. Isolation Forest
5. One-Class SVM (novelty detection)

Pregunta del usuario: {body.question}

Responde en espanol, de forma clara y concisa. Si la pregunta es sobre una alerta especifica, explica que detecto y por que se disparo. Si no tienes informacion suficiente, dilo claramente."""

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
"""
    try:
        response = req.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json"},
            json={
                "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        answer = response.json()["content"][0]["text"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en Claude API: {e}")

    return {
        "question": body.question,
        "answer": answer,
        "context_alerts": len(alerts),
        "timestamp_utc": datetime.now(timezone.utc).isoformat()
    }
"""

@app.post("/trigger")
def trigger_detection():
    """
    Corre el detector manualmente sobre la ventana actual.
    Util para pruebas o para forzar un ciclo sin esperar el pipeline.
    """
    try:
        from detector import run_detection
        import glob

        files = sorted(glob.glob("data/logs_*.csv"), reverse=True)
        if not files:
            raise HTTPException(status_code=404, detail="No hay CSVs. Corre pipeline.py primero.")

        df = pd.read_csv(files[0])
        window = files[0].replace("data/logs_", "").replace(".csv", "")

        run_detection(df, window_start=window)

        return {
            "status": "detection complete",
            "window": window,
            "records_analyzed": len(df),
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/notify-pipeline-down")
def notify_pipeline_down():
    """
    Endpoint para notificar por email cuando el pipeline deja de hacer llamadas.
    Se llama desde un cron job o monitor externo.
    """
    sent = send_email_alert(
        subject="NOVA ALERTA: Pipeline caido",
        body=(
            f"El pipeline de NOVA no ha hecho llamadas a la API de SAP en los ultimos 30 minutos.\n\n"
            f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
            f"Accion requerida: revisar Railway/BTP y reiniciar el worker si es necesario."
        )
    )
    return {"email_sent": sent, "timestamp_utc": datetime.now(timezone.utc).isoformat()}
