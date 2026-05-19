import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

# ── Config ────────────────────────────────────────────────────────
API_BASE = os.getenv("API_BASE")

st.set_page_config(
    page_title="NOVA · SAP Threat Detection",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── SAP Theme CSS ─────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=72+Brand+Variable:wght@400;700;900&display=swap');

/* SAP Color Palette */
:root {
    --sap-blue:        #0070F2;
    --sap-dark-blue:   #003b6c;
    --sap-shell:       #1C2B39;
    --sap-bg:          #F2F4F8;
    --sap-white:       #FFFFFF;
    --sap-border:      #D9DBDD;
    --sap-text:        #1A1E26;
    --sap-muted:       #556B82;
    --sap-success:     #188918;
    --sap-warning:     #E76500;
    --sap-error:       #BB0000;
    --sap-medium:      #E76500;
    --sap-high:        #BB0000;
}

/* Global */
html, body, [class*="css"] {
    font-family: '72 Brand Variable', 'SAP-icons', Arial, sans-serif;
    background-color: var(--sap-bg) !important;
    color: var(--sap-text);
}

/* Hide default Streamlit header */
#MainMenu, footer, header { visibility: hidden; }

/* Top shell bar */
.nova-shell {
    background: var(--sap-shell);
    color: white;
    padding: 12px 32px;
    display: flex;
    align-items: center;
    gap: 16px;
    margin: -1rem -1rem 2rem -1rem;
    border-bottom: 3px solid var(--sap-blue);
}
.nova-shell .product-name {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 0.04em;
    color: white;
}
.nova-shell .app-name {
    font-size: 13px;
    color: #9DBDD6;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.nova-shell .divider {
    width: 1px;
    height: 32px;
    background: #2E4A5E;
    margin: 0 8px;
}

/* Metric cards */
.metric-card {
    background: var(--sap-white);
    border: 1px solid var(--sap-border);
    border-top: 3px solid var(--sap-blue);
    border-radius: 4px;
    padding: 20px 24px;
    margin-bottom: 16px;
}
.metric-card.high { border-top-color: var(--sap-high); }
.metric-card.medium { border-top-color: var(--sap-medium); }
.metric-card.success { border-top-color: var(--sap-success); }

.metric-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--sap-muted);
    margin-bottom: 6px;
}
.metric-value {
    font-size: 36px;
    font-weight: 900;
    color: var(--sap-text);
    line-height: 1;
}
.metric-sub {
    font-size: 12px;
    color: var(--sap-muted);
    margin-top: 4px;
}

/* Section headers */
.section-header {
    font-size: 14px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--sap-muted);
    border-bottom: 1px solid var(--sap-border);
    padding-bottom: 8px;
    margin: 24px 0 16px 0;
}

/* Alert badge */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 2px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.badge.HIGH   { background: #FFEAEA; color: var(--sap-high); border: 1px solid #FFBDBD; }
.badge.MEDIUM { background: #FFF3E8; color: var(--sap-medium); border: 1px solid #FCCFA1; }
.badge.LOW    { background: #E8F5E9; color: var(--sap-success); border: 1px solid #A5D6A7; }

/* Status indicator */
.status-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-right: 6px;
}
.status-dot.online  { background: var(--sap-success); box-shadow: 0 0 6px var(--sap-success); }
.status-dot.offline { background: var(--sap-error);   box-shadow: 0 0 6px var(--sap-error); }

/* Chat */
.chat-bubble-user {
    background: var(--sap-blue);
    color: white;
    border-radius: 4px 4px 0 4px;
    padding: 12px 16px;
    margin: 8px 0 8px 40px;
    font-size: 14px;
}
.chat-bubble-bot {
    background: var(--sap-white);
    border: 1px solid var(--sap-border);
    border-radius: 4px 4px 4px 0;
    padding: 12px 16px;
    margin: 8px 40px 8px 0;
    font-size: 14px;
    color: var(--sap-text);
}
.chat-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--sap-muted);
    margin-bottom: 4px;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: var(--sap-shell) !important;
}
[data-testid="stSidebar"] * {
    color: #C8D9E8 !important;
}
[data-testid="stSidebar"] .stRadio label {
    font-size: 13px;
}

/* Buttons */
.stButton > button {
    background: var(--sap-blue) !important;
    color: white !important;
    border: none !important;
    border-radius: 4px !important;
    font-weight: 600 !important;
    letter-spacing: 0.04em !important;
    padding: 8px 20px !important;
    transition: background 0.2s;
}
.stButton > button:hover {
    background: var(--sap-dark-blue) !important;
}

/* Input */
.stTextInput > div > div > input,
.stTextArea textarea {
    border: 1px solid var(--sap-border) !important;
    border-radius: 4px !important;
    font-family: inherit !important;
}
.stTextInput > div > div > input:focus,
.stTextArea textarea:focus {
    border-color: var(--sap-blue) !important;
    box-shadow: 0 0 0 2px rgba(0,112,242,0.15) !important;
}

/* Table */
.stDataFrame { border: 1px solid var(--sap-border) !important; border-radius: 4px; }

/* Monospace for timestamps */
.mono { font-family: 'IBM Plex Mono', monospace; font-size: 12px; }
</style>
""", unsafe_allow_html=True)


# ── Shell Bar ─────────────────────────────────────────────────────
st.markdown("""
<div class="nova-shell">
    <span style="font-size:24px;">🛡️</span>
    <div class="divider"></div>
    <div>
        <div class="product-name">NOVA</div>
        <div class="app-name">SAP Threat Detection System</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Navigation")
    page = st.radio(
        "",
        ["📊 Dashboard", "🚨 Alerts", "💬 Chat NOVA", "🔧 Controls"],
        label_visibility="collapsed"
    )
    st.markdown("---")
    st.markdown(f"<div style='font-size:11px;color:#556B82;'>API: {API_BASE}</div>", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────
def api_get(path, params=None):
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=8)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)

def api_post(path, payload=None):
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload, timeout=30)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)

def badge(severity):
    s = str(severity).upper()
    return f'<span class="badge {s}">{s}</span>'


# ══════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ══════════════════════════════════════════════════════════════════
if page == "📊 Dashboard":
    status, err = api_get("/status")

    if err:
        st.error(f"No se pudo conectar a la API: {err}")
        st.stop()

    sap_online = status.get("sap_server") == "ok"
    dot_class  = "online" if sap_online else "offline"
    dot_label  = "Online" if sap_online else "Offline"

    st.markdown(f"""
    <div style="display:flex;align-items:center;margin-bottom:24px;">
        <span class="status-dot {dot_class}"></span>
        <span style="font-size:13px;font-weight:600;color:{'#188918' if sap_online else '#BB0000'};">
            SAP Server {dot_label}
        </span>
        <span style="margin-left:24px;font-size:12px;color:#556B82;" class="mono">
            Ventana activa: {status.get('window_start','—')[:19] if status.get('window_start') else '—'}
        </span>
    </div>
    """, unsafe_allow_html=True)

    # KPI row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Total Alertas</div>
            <div class="metric-value">{status.get('total_alerts', 0)}</div>
            <div class="metric-sub">Históricas acumuladas</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="metric-card high">
            <div class="metric-label">🔴 Alta Severidad</div>
            <div class="metric-value" style="color:#BB0000;">{status.get('high_alerts', 0)}</div>
            <div class="metric-sub">Requieren atención inmediata</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="metric-card medium">
            <div class="metric-label">🟠 Media Severidad</div>
            <div class="metric-value" style="color:#E76500;">{status.get('medium_alerts', 0)}</div>
            <div class="metric-sub">Monitoreo activo</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="metric-card success">
            <div class="metric-label">📦 Registros SAP</div>
            <div class="metric-value" style="color:#188918;">{status.get('total_records', '—')}</div>
            <div class="metric-sub">En ventana activa</div>
        </div>""", unsafe_allow_html=True)

    # Last alert
    last = status.get("last_alert")
    if last:
        st.markdown('<div class="section-header">Última Alerta</div>', unsafe_allow_html=True)
        col_a, col_b = st.columns([1, 3])
        with col_a:
            st.markdown(badge(last.get("severity", "?")), unsafe_allow_html=True)
            st.markdown(f"<div style='font-size:13px;font-weight:700;margin-top:8px;'>{last.get('alert_type','—')}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='mono' style='color:#556B82;'>{str(last.get('timestamp_utc',''))[:19]}</div>", unsafe_allow_html=True)
        with col_b:
            st.markdown(f"<div style='background:white;border:1px solid #D9DBDD;border-radius:4px;padding:12px 16px;font-size:13px;'>{last.get('message','Sin mensaje')}</div>", unsafe_allow_html=True)

    # Detection layers
    st.markdown('<div class="section-header">Capas de Detección</div>', unsafe_allow_html=True)
    layers = [
        ("1", "Reglas Dinámicas", "MAD 3-sigma con umbrales adaptativos", "🔵"),
        ("2", "Z-Score Robusto", "Análisis histórico de desviación estándar", "🔵"),
        ("3", "Detección por App SAP", "Clasificación por módulo de aplicación", "🔵"),
        ("4", "Isolation Forest", "Detección de anomalías no supervisada", "🔵"),
        ("5", "One-Class SVM", "Novelty detection para patrones nuevos", "🔵"),
    ]
    cols = st.columns(5)
    for i, (num, name, desc, icon) in enumerate(layers):
        with cols[i]:
            st.markdown(f"""
            <div style="background:white;border:1px solid #D9DBDD;border-radius:4px;
                        padding:16px;text-align:center;height:120px;">
                <div style="font-size:22px;font-weight:900;color:#0070F2;">{num}</div>
                <div style="font-size:12px;font-weight:700;margin:6px 0 4px;">{name}</div>
                <div style="font-size:11px;color:#556B82;">{desc}</div>
            </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# PAGE: ALERTS
# ══════════════════════════════════════════════════════════════════
elif page == "🚨 Alerts":
    st.markdown('<div class="section-header">Historial de Alertas</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([1, 3])
    with col1:
        severity_filter = st.selectbox("Severidad", ["Todas", "HIGH", "MEDIUM"])
    with col2:
        limit = st.slider("Límite de registros", 10, 200, 50)

    params = {"limit": limit}
    if severity_filter != "Todas":
        params["severity"] = severity_filter

    alerts, err = api_get("/alerts", params=params)

    if err:
        st.error(f"Error: {err}")
    elif not alerts or not alerts.get("alerts"):
        st.info("No hay alertas registradas.")
    else:
        data = alerts["alerts"]
        st.markdown(f"<div style='font-size:13px;color:#556B82;margin-bottom:12px;'>Mostrando <b>{len(data)}</b> de <b>{alerts['total']}</b> alertas</div>", unsafe_allow_html=True)

        for a in data:
            sev = str(a.get("severity", "?")).upper()
            color = "#BB0000" if sev == "HIGH" else "#E76500" if sev == "MEDIUM" else "#188918"
            border = f"3px solid {color}"

            st.markdown(f"""
            <div style="background:white;border:1px solid #D9DBDD;border-left:{border};
                        border-radius:4px;padding:14px 18px;margin-bottom:8px;">
                <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px;">
                    {badge(sev)}
                    <span style="font-weight:700;font-size:13px;">{a.get('alert_type','—')}</span>
                    <span class="mono" style="color:#556B82;margin-left:auto;">{str(a.get('timestamp_utc',''))[:19]}</span>
                </div>
                <div style="font-size:13px;color:#1A1E26;">{a.get('message','Sin mensaje')}</div>
            </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# PAGE: CHAT
# ══════════════════════════════════════════════════════════════════
elif page == "💬 Chat NOVA":
    st.markdown('<div class="section-header">Asistente NOVA · Powered by Gemini</div>', unsafe_allow_html=True)
    st.markdown("<div style='font-size:13px;color:#556B82;margin-bottom:20px;'>Pregúntale a NOVA sobre las alertas del sistema en lenguaje natural.</div>", unsafe_allow_html=True)

    # Chat history
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Suggested questions
    suggestions = [
        "¿Qué pasó esta noche?",
        "¿Cuáles son las alertas HIGH?",
        "¿Por qué se disparó el Isolation Forest?",
        "Resume la actividad reciente",
    ]
    st.markdown("<div style='font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#556B82;margin-bottom:8px;'>Preguntas sugeridas:</div>", unsafe_allow_html=True)
    cols = st.columns(4)
    for i, s in enumerate(suggestions):
        with cols[i]:
            if st.button(s, key=f"sug_{i}"):
                st.session_state.pending_question = s

    st.markdown("---")

    # Display history
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(f"""
            <div class="chat-label" style="text-align:right;">Tú</div>
            <div class="chat-bubble-user">{msg['content']}</div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="chat-label">🛡️ NOVA</div>
            <div class="chat-bubble-bot">{msg['content']}</div>
            """, unsafe_allow_html=True)

    # Input
    question = st.text_input(
        "Escribe tu pregunta...",
        value=st.session_state.pop("pending_question", ""),
        placeholder="¿Qué anomalías detectó NOVA esta noche?",
        label_visibility="collapsed"
    )

    col_send, col_clear = st.columns([1, 5])
    with col_send:
        send = st.button("Enviar →", use_container_width=True)
    with col_clear:
        if st.button("Limpiar chat", use_container_width=False):
            st.session_state.chat_history = []
            st.rerun()

    if send and question.strip():
        st.session_state.chat_history.append({"role": "user", "content": question})
        with st.spinner("NOVA está analizando..."):
            result, err = api_post("/chat", {"question": question})
        if err:
            answer = f"Error al conectar con la API: {err}"
        else:
            answer = result.get("answer", "Sin respuesta.")
        st.session_state.chat_history.append({"role": "assistant", "content": answer})
        st.rerun()


# ══════════════════════════════════════════════════════════════════
# PAGE: CONTROLS
# ══════════════════════════════════════════════════════════════════
elif page == "🔧 Controls":
    st.markdown('<div class="section-header">Controles del Sistema</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        <div style="background:white;border:1px solid #D9DBDD;border-radius:4px;padding:20px;">
            <div style="font-weight:700;margin-bottom:8px;">▶ Trigger Detection</div>
            <div style="font-size:13px;color:#556B82;margin-bottom:16px;">
                Corre el detector manualmente sobre la ventana actual de logs SAP.
            </div>
        </div>""", unsafe_allow_html=True)
        if st.button("🚀 Ejecutar Detección", use_container_width=True):
            with st.spinner("Corriendo pipeline de detección..."):
                result, err = api_post("/trigger")
            if err:
                st.error(f"Error: {err}")
            else:
                st.success(f"✅ Detección completada — {result.get('records_analyzed', '?')} registros analizados en ventana {result.get('window','?')}")

    with col2:
        st.markdown("""
        <div style="background:white;border:1px solid #D9DBDD;border-radius:4px;padding:20px;">
            <div style="font-weight:700;margin-bottom:8px;">📧 Notificar Pipeline Down</div>
            <div style="font-size:13px;color:#556B82;margin-bottom:16px;">
                Envía alerta por email si el pipeline dejó de hacer llamadas a SAP.
            </div>
        </div>""", unsafe_allow_html=True)
        if st.button("📨 Enviar Notificación", use_container_width=True):
            with st.spinner("Enviando email..."):
                result, err = api_post("/notify-pipeline-down")
            if err:
                st.error(f"Error: {err}")
            else:
                sent = result.get("email_sent", False)
                if sent:
                    st.success("✅ Email enviado correctamente.")
                else:
                    st.warning("⚠️ Email no enviado — revisa configuración SMTP en .env")

    # Baseline viewer
    st.markdown('<div class="section-header">Baseline del Modelo</div>', unsafe_allow_html=True)
    if st.button("📋 Ver Baseline Actual"):
        baseline, err = api_get("/baseline")
        if err:
            st.error(f"Error: {err}")
        else:
            st.json(baseline)