import streamlit as st
import pandas as pd
import glob
import os
import requests
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Loading environment variables for SAP API and NOVA API
TOKEN   = os.getenv("SAP_TOKEN")
BASE    = os.getenv("SAP_BASE_URL")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
API_URL = os.getenv("NOVA_API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="NOVA - SAP SOC",
    page_icon="NOVA",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&family=Playfair+Display:wght@600;700&display=swap');

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background-color: #f8f7fc !important;
    color: #1a1025 !important;
    font-family: 'DM Sans', sans-serif !important;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #ede8f5 !important;
}
[data-testid="stSidebar"] * { color: #3d2870 !important; }

h1, h2, h3, h4 {
    font-family: 'Playfair Display', serif !important;
    color: #1a1025 !important;
    letter-spacing: -0.01em;
}

[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #ede8f5;
    border-top: 3px solid #7c3aed;
    border-radius: 10px;
    padding: 18px 20px !important;
    box-shadow: 0 1px 4px rgba(124,58,237,0.06);
    transition: box-shadow 0.2s;
}
[data-testid="stMetric"]:hover { box-shadow: 0 4px 16px rgba(124,58,237,0.12); }
[data-testid="stMetricLabel"] {
    color: #7c3aed !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.65rem !important;
    text-transform: uppercase;
    letter-spacing: 0.12em;
}
[data-testid="stMetricValue"] {
    color: #1a1025 !important;
    font-family: 'Playfair Display', serif !important;
    font-size: 1.7rem !important;
    font-weight: 700;
}

[data-testid="stTabs"] button {
    font-family: 'DM Mono', monospace !important;
    color: #9b8ab4 !important;
    font-size: 0.68rem !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    border-bottom: 2px solid transparent !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #5b21b6 !important;
    border-bottom: 2px solid #7c3aed !important;
}

[data-testid="stDataFrame"] {
    border: 1px solid #ede8f5 !important;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}

.stButton > button {
    background: #7c3aed !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.7rem !important;
    letter-spacing: 0.06em;
    transition: background 0.2s;
}
.stButton > button:hover {
    background: #5b21b6 !important;
    box-shadow: 0 4px 12px rgba(124,58,237,0.3);
}

.stTextInput > div > div > input {
    background: #ffffff !important;
    border: 1px solid #ede8f5 !important;
    color: #1a1025 !important;
    border-radius: 8px !important;
}
.stTextInput > div > div > input:focus {
    border-color: #7c3aed !important;
    box-shadow: 0 0 0 3px rgba(124,58,237,0.1) !important;
}

[data-testid="stSelectbox"] > div > div {
    background: #ffffff !important;
    border: 1px solid #ede8f5 !important;
    color: #1a1025 !important;
    border-radius: 8px !important;
}

hr { border-color: #ede8f5 !important; }

[data-testid="stAlert"] {
    background: #faf8ff !important;
    border: 1px solid #ede8f5 !important;
    border-left: 3px solid #7c3aed !important;
    border-radius: 8px !important;
    color: #1a1025 !important;
}

[data-testid="stAlert"] *,
[data-testid="stAlert"] p,
[data-testid="stAlert"] span,
[data-testid="stAlert"] div {
    color: #1a1025 !important;
}

::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: #f8f7fc; }
::-webkit-scrollbar-thumb { background: #c4b5fd; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #7c3aed; }

.label-mono {
    font-family: 'DM Mono', monospace;
    font-size: 0.65rem;
    color: #9b8ab4;
    text-transform: uppercase;
    letter-spacing: 0.12em;
}
.section-title {
    font-family: 'Playfair Display', serif;
    font-size: 1.15rem;
    font-weight: 700;
    color: #1a1025;
    margin-bottom: 4px;
}
.attack-card {
    background: #ffffff;
    border: 1px solid #ede8f5;
    border-radius: 10px;
    padding: 18px 22px;
    margin-bottom: 16px;
    box-shadow: 0 1px 6px rgba(124,58,237,0.06);
}
.attack-card-red    { border-left: 4px solid #dc2626; }
.attack-card-orange { border-left: 4px solid #d97706; }
.attack-card-purple { border-left: 4px solid #7c3aed; }
</style>
""", unsafe_allow_html=True)


# Header 
col_logo, col_title, col_time = st.columns([1, 7, 2])
with col_logo:
    st.markdown("""
    <svg width="56" height="56" viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="56" height="56" rx="14" fill="#7c3aed"/>
      <polygon points="28,8 50,46 6,46" fill="none" stroke="white" stroke-width="2.5"/>
      <polygon points="28,17 42,41 14,41" fill="none" stroke="white" stroke-width="1.2" opacity="0.5"/>
      <circle cx="28" cy="33" r="3.5" fill="white"/>
      <line x1="28" y1="17" x2="28" y2="29.5" stroke="white" stroke-width="1.5"/>
    </svg>
    """, unsafe_allow_html=True)

with col_title:
    st.markdown("""
    <div style="padding-top: 6px;">
        <div style="font-family: 'Playfair Display', serif; font-size: 1.9rem; font-weight: 700;
                    color: #1a1025; line-height: 1.1;">NOVA</div>
        <div style="font-family: 'DM Mono', monospace; font-size: 0.65rem; color: #9b8ab4;
                    letter-spacing: 0.15em; text-transform: uppercase; margin-top: 2px;">
            SAP Security Operations Center &nbsp;·&nbsp; Hack IDM x SAP 2026
        </div>
    </div>
    """, unsafe_allow_html=True)

with col_time:
    st.markdown(f"""
    <div style="text-align: right; padding-top: 10px;">
        <div style="font-family: 'DM Mono', monospace; font-size: 0.65rem; color: #9b8ab4;
                    text-transform: uppercase; letter-spacing: 0.1em;">UTC</div>
        <div style="font-family: 'Playfair Display', serif; font-size: 1.1rem;
                    color: #7c3aed; font-weight: 600;">{datetime.utcnow().strftime('%H:%M:%S')}</div>
        <div style="font-family: 'DM Mono', monospace; font-size: 0.6rem; color: #c4b5fd;">
            {datetime.utcnow().strftime('%d %b %Y')}
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<hr style='margin: 10px 0 20px'>", unsafe_allow_html=True)

# DATA LOADERS
@st.cache_data(ttl=60)
def load_from_hana():
    try:
        from hana import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT window_id, log_type, application, http_status_code,
                          client_ip, llm_cost_usd, llm_response_time_ms, llm_provider, region
                          FROM SAP_LOGS""")
        rows = cursor.fetchall()
        cols = ["_window","sap_function_log_type","sap_function_application",
                "http_status_code","client_ip","llm_cost_usd","llm_response_time_ms",
                "llm_provider","region"]
        cursor.close(); conn.close()
        return pd.DataFrame(rows, columns=cols)
    except Exception as e:
        st.error(f"HANA error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def load_alerts_from_hana():
    try:
        from hana import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT timestamp_utc, alert_type, severity, message,
                          status_code, window_start, response_ms
                          FROM SAP_ALERTS ORDER BY created_at DESC""")
        rows = cursor.fetchall()
        cols = ["timestamp_utc","alert_type","severity","message",
                "status_code","window_start","response_ms"]
        cursor.close(); conn.close()
        return pd.DataFrame(rows, columns=cols)
    except Exception as e:
        st.error(f"HANA alerts error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def load_all_csv():
    files = sorted(glob.glob("data/logs_*.csv"))
    if not files:
        return pd.DataFrame()
    dfs = []
    for f in files:
        tmp = pd.read_csv(f)
        tmp["_window"] = os.path.basename(f).replace("logs_","").replace(".csv","")
        dfs.append(tmp)
    return pd.concat(dfs, ignore_index=True)

@st.cache_data(ttl=60)
def load_alerts_csv():
    path = "data/alerts_log.csv"
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path, on_bad_lines="skip")
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def api_get_status():
    try:
        r = requests.get(f"{API_URL}/status", timeout=5)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

@st.cache_data(ttl=30)
def api_get_alerts(limit=100, severity=None):
    try:
        params = {"limit": limit}
        if severity:
            params["severity"] = severity
        r = requests.get(f"{API_URL}/alerts", params=params, timeout=5)
        return r.json()
    except Exception as e:
        return {"error": str(e), "alerts": []}

@st.cache_data(ttl=60)
def api_get_baseline():
    try:
        r = requests.get(f"{API_URL}/baseline", timeout=5)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def api_trigger():
    try:
        r = requests.post(f"{API_URL}/trigger", timeout=30)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def api_chat(question: str):
    try:
        r = requests.post(f"{API_URL}/chat", json={"question": question}, timeout=30)
        return r.json()
    except Exception as e:
        return {"error": str(e), "answer": f"Error conectando con la API: {e}"}

def fmt_time(ms):
    if pd.isna(ms):
        return "-"
    ms = int(ms)
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms//60000}m {(ms%60000)//1000}s {ms%1000}ms"

# SIDEBAR
with st.sidebar:
    st.markdown("""
    <div style="font-family: 'DM Mono', monospace; font-size: 0.6rem; color: #9b8ab4;
                text-transform: uppercase; letter-spacing: 0.14em; margin-bottom: 14px;">
        Configuración
    </div>
    """, unsafe_allow_html=True)

    data_source = st.radio("Fuente de datos", ["HANA Cloud", "CSV local"], index=1)

    st.markdown("<hr>", unsafe_allow_html=True)

    try:
        health_check = requests.get(f"{API_URL}/", timeout=3).json()
        api_ok = health_check.get("status") == "online"
    except Exception:
        api_ok = False

    sc = "#16a34a" if api_ok else "#dc2626"
    st_txt = "ONLINE" if api_ok else "OFFLINE"
    st.markdown(f"""
    <div style="display:flex; align-items:center; gap:8px; margin-bottom:16px;
                background:#faf8ff; border:1px solid #ede8f5; border-radius:8px; padding:10px 14px;">
        <div style="width:7px;height:7px;border-radius:50%;background:{sc};box-shadow:0 0 5px {sc};"></div>
        <span style="font-family:'DM Mono',monospace;font-size:0.68rem;color:{sc};font-weight:500;">
            API NOVA &nbsp;·&nbsp; {st_txt}
        </span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    auto_refresh = st.toggle("Auto-refresh", value=False)
    refresh_interval = st.selectbox("Intervalo", [30, 60, 120], index=1,
                                    format_func=lambda x: f"{x}s")

    st.markdown("<hr>", unsafe_allow_html=True)

    if st.button("Actualizar ahora", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    if st.button("Correr detección", use_container_width=True):
        with st.spinner("Analizando..."):
            result = api_trigger()
        if "error" in result:
            st.error(result["error"])
        else:
            st.success(f"Completado: {result.get('records_analyzed','?')} registros")

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown(f"""
    <div style="font-family:'DM Mono',monospace;font-size:0.6rem;color:#9b8ab4;line-height:2;">
        Última actualización<br>
        <span style="color:#7c3aed;font-size:0.75rem;">{datetime.utcnow().strftime('%H:%M:%S')} UTC</span>
    </div>
    """, unsafe_allow_html=True)

# STATUS BAR
st.markdown('<div class="label-mono" style="margin-bottom:10px;">Estado del sistema</div>',
            unsafe_allow_html=True)

status_data = api_get_status()
c1, c2, c3 = st.columns(3) #c4, c5, c6 = st.columns(6)

try:
    health = requests.get(f"{BASE}/health", timeout=5).json()
    c1.metric("Servidor SAP", "OK" if health.get("status") == "ok" else "DOWN")
except Exception:
    c1.metric("Servidor SAP", "Sin conexión")

try:
    info = requests.get(f"{BASE}/info", headers=HEADERS, timeout=5).json()
    c2.metric("Registros (ventana)", f"{info.get('total_records',0):,}")
    w_start = info.get('window_start','?')[11:16]
    w_end   = info.get('window_end','?')[11:16]
    c3.metric("Ventana activa", f"{w_start} - {w_end} UTC")
except Exception:
    c2.metric("Registros", "-")
    c3.metric("Ventana", "-")

c4, c5, c6 = st.columns(3)

c4.metric("Alertas totales", status_data.get("total_alerts", "-"))
c5.metric("HIGH",            status_data.get("high_alerts",  "-"))
c6.metric("MEDIUM",          status_data.get("medium_alerts","-"))

# Cargar datos principales 
if data_source == "HANA Cloud":
    df_all = load_from_hana()
    alerts_df = load_alerts_from_hana()
else:
    #dir_data =  os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_files = sorted(glob.glob(f"data/logs_*.csv"))
    df_all = load_all_csv()
    alerts_df = load_alerts_csv()

if df_all.empty:
    st.warning("No hay datos aún. Corre pipeline.py.")
    st.stop()

st.markdown("<hr style='margin:20px 0'>", unsafe_allow_html=True)

LOG_CRITICOS = ["LLM_ERROR","LLM_TIMEOUT","SECURITY","ERROR","WARNING"]

# TABS
(tab_general, tab_live, tab_ataques,
 tab_baseline, tab_chat) = st.tabs([
    "Vista General",
    "Monitoreo en vivo",
    "Ataques detectados",
    "Baseline del modelo",
    "Asistente NOVA",
])

# TAB 1 — VISTA GENERAL 
with tab_general:

    st.markdown('<div class="section-title">Tendencias históricas — todas las ventanas</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="label-mono" style="margin-bottom:12px;">Conteo por tipo de log en cada ventana capturada</div>',
                unsafe_allow_html=True)

    pivot = (
        df_all[df_all["sap_function_log_type"].isin(LOG_CRITICOS)]
        .groupby(["_window","sap_function_log_type"])
        .size().unstack(fill_value=0).sort_index()
    )
    pivot.index = [w[9:13]+":"+w[13:15] for w in pivot.index]
    st.line_chart(pivot, height=280)

    st.markdown("<hr>", unsafe_allow_html=True)
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown('<div class="section-title">Historial de alertas enviadas</div>',
                    unsafe_allow_html=True)
        if alerts_df is not None and not alerts_df.empty:
            alerts_sorted = alerts_df.sort_values("timestamp_utc", ascending=False)
            total  = len(alerts_sorted)
            high   = len(alerts_sorted[alerts_sorted["severity"]=="HIGH"])
            medium = len(alerts_sorted[alerts_sorted["severity"]=="MEDIUM"])

            if "response_ms" in alerts_sorted.columns:
                valid_times = alerts_sorted["response_ms"].dropna()
                avg_ms = valid_times.mean()
                min_ms = valid_times.min()
                a1, a2, a3, a4 = st.columns(4)
                a1.metric("Total alertas", total)
                a2.metric("HIGH",   high)
                a3.metric("MEDIUM", medium)
                a4.metric("MTTD promedio", fmt_time(avg_ms))
                st.markdown(f'<div class="label-mono" style="margin-bottom:8px;">MTTD mínimo: {fmt_time(min_ms)}</div>',
                            unsafe_allow_html=True)
            else:
                a1, a2, a3 = st.columns(3)
                a1.metric("Total alertas", total)
                a2.metric("HIGH",   high)
                a3.metric("MEDIUM", medium)

            cols_show = [c for c in ["timestamp_utc","severity","alert_type","message"]
                         if c in alerts_sorted.columns]
            st.dataframe(alerts_sorted[cols_show], use_container_width=True, height=300,
                         hide_index=True,
                         column_config={"timestamp_utc":"Hora UTC","severity":"Severidad",
                                        "alert_type":"Tipo","message":"Mensaje"})
        else:
            st.info("No hay alertas registradas.")

    with col_right:
        st.markdown('<div class="section-title">Análisis LLM</div>', unsafe_allow_html=True)
        llm_df = df_all[df_all["sap_function_log_type"].isin(
            ["LLM_REQUEST","LLM_ERROR","LLM_TIMEOUT"])].copy()
        llm_df["llm_cost_usd"]         = pd.to_numeric(llm_df.get("llm_cost_usd"), errors="coerce")
        llm_df["llm_response_time_ms"] = pd.to_numeric(llm_df.get("llm_response_time_ms"), errors="coerce")

        total_llm  = len(llm_df)
        llm_errors = len(llm_df[llm_df["sap_function_log_type"].isin(["LLM_ERROR","LLM_TIMEOUT"])])
        error_rate = llm_errors / total_llm * 100 if total_llm > 0 else 0
        avg_cost   = llm_df["llm_cost_usd"].mean()
        max_cost   = llm_df["llm_cost_usd"].max()

        b1, b2, b3 = st.columns(3)
        b1.metric("Tasa de error LLM", f"{error_rate:.1f}%")
        b2.metric("Costo promedio",    f"${avg_cost:.4f}")
        b3.metric("Costo máximo",      f"${max_cost:.4f}")

        cost_by_window = (
            llm_df[llm_df["sap_function_log_type"]=="LLM_REQUEST"]
            .groupby("_window")["llm_cost_usd"].mean().sort_index()
        )
        cost_by_window.index = [w[9:13]+":"+w[13:15] for w in cost_by_window.index]
        st.markdown('<div class="label-mono" style="margin:10px 0 4px;">Costo LLM promedio por ventana</div>',
                    unsafe_allow_html=True)
        st.line_chart(cost_by_window, height=160)

    st.markdown("<hr>", unsafe_allow_html=True)

    # Actividad por semana
    st.markdown('<div class="section-title">Actividad por semana</div>', unsafe_allow_html=True)
    st.markdown('<div class="label-mono" style="margin-bottom:16px;">Time series por semana calendario · ventanas de 30 min</div>',
                unsafe_allow_html=True)

    SEMANAS = [
        ("18-24 May",      "20260518", "20260524"),
        ("11-17 May",      "20260511", "20260517"),
        ("4-10 May",       "20260504", "20260510"),
        ("30 Abr - 3 May", "20260430", "20260503"),
    ]

    for sem_label, start, end in SEMANAS:
        df_week = df_all[
            (df_all["_window"] >= start) & (df_all["_window"] <= f"{end}_2359")
        ].copy()
        if df_week.empty:
            continue

        st.markdown(f"""
        <div style="font-family:'DM Mono',monospace;font-size:0.75rem;font-weight:500;
                    color:#5b21b6;margin:16px 0 6px;letter-spacing:0.04em;">
            Semana {sem_label}
        </div>""", unsafe_allow_html=True)

        pivot_week = (
            df_week[df_week["sap_function_log_type"].isin(LOG_CRITICOS)]
            .groupby(["_window","sap_function_log_type"])
            .size().unstack(fill_value=0).sort_index()
        )
        pivot_week.index = [f"{w[6:8]}/{w[4:6]} {w[9:11]}:{w[11:13]}" for w in pivot_week.index]
        st.line_chart(pivot_week, height=220)


# TAB 2 — MONITOREO EN VIVO 
with tab_live:
    alerts_api_data = api_get_alerts(limit=100)
    alerts_api_list = alerts_api_data.get("alerts", [])
    alerts_api_df   = pd.DataFrame(alerts_api_list) if alerts_api_list else pd.DataFrame()

    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.markdown('<div class="section-title">Alertas en tiempo real</div>', unsafe_allow_html=True)
        st.markdown('<div class="label-mono" style="margin-bottom:12px;">Desde FastAPI · /alerts</div>',
                    unsafe_allow_html=True)

        f1, f2 = st.columns(2)
        with f1:
            sev_filter = st.selectbox("Severidad", ["Todas","HIGH","MEDIUM"], key="sev_live")
        with f2:
            type_filter = st.selectbox("Tipo", ["Todos"] + list(
                {a.get("alert_type","") for a in alerts_api_list if a.get("alert_type")}
            ), key="type_live")

        df_show = alerts_api_df.copy()
        if not df_show.empty:
            if sev_filter != "Todas":
                df_show = df_show[df_show["severity"] == sev_filter]
            if type_filter != "Todos":
                df_show = df_show[df_show["alert_type"] == type_filter]
            cols_show = [c for c in ["timestamp_utc","severity","alert_type","message"]
                         if c in df_show.columns]
            st.dataframe(
                df_show[cols_show].sort_values("timestamp_utc", ascending=False),
                use_container_width=True, height=400, hide_index=True,
                column_config={
                    "timestamp_utc": st.column_config.TextColumn("Hora UTC", width=160),
                    "severity":      st.column_config.TextColumn("Severidad", width=90),
                    "alert_type":    st.column_config.TextColumn("Tipo", width=160),
                    "message":       st.column_config.TextColumn("Mensaje"),
                }
            )
        else:
            st.info("Sin alertas desde la API. Asegurate de que FastAPI este corriendo.")

    with col_right:
        st.markdown('<div class="section-title">Distribución</div>', unsafe_allow_html=True)
        if not alerts_api_df.empty and "severity" in alerts_api_df.columns:
            st.markdown('<div class="label-mono" style="margin-bottom:6px;">Por severidad</div>',
                        unsafe_allow_html=True)
            st.bar_chart(alerts_api_df["severity"].value_counts(), height=160, color="#7c3aed")

            if "alert_type" in alerts_api_df.columns:
                st.markdown('<div class="label-mono" style="margin:10px 0 6px;">Por tipo de detección</div>',
                            unsafe_allow_html=True)
                st.bar_chart(alerts_api_df["alert_type"].value_counts().head(8), height=180, color="#a78bfa")

        if not alerts_api_df.empty and "response_ms" in alerts_api_df.columns:
            valid = alerts_api_df["response_ms"].dropna()
            if len(valid) > 0:
                st.markdown('<div class="label-mono" style="margin:10px 0 8px;">Tiempos de detección</div>',
                            unsafe_allow_html=True)
                t1, t2, t3 = st.columns(3)
                t1.metric("Promedio", fmt_time(valid.mean()))
                t2.metric("Mínimo",   fmt_time(valid.min()))
                t3.metric("Máximo",   fmt_time(valid.max()))

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">Tendencia histórica de logs</div>', unsafe_allow_html=True)
    st.markdown('<div class="label-mono" style="margin-bottom:12px;">Eventos criticos por ventana · CSV local</div>',
                unsafe_allow_html=True)

    if not df_all.empty:
        pivot_live = (
            df_all[df_all["sap_function_log_type"].isin(LOG_CRITICOS)]
            .groupby(["_window","sap_function_log_type"])
            .size().unstack(fill_value=0).sort_index()
        )
        pivot_live.index = [w[9:13]+":"+w[13:15] for w in pivot_live.index]
        st.line_chart(pivot_live, height=240)
    else:
        st.info("Sin datos CSV. Corre pipeline.py para capturar logs.")

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">Explorar logs por ventana</div>', unsafe_allow_html=True)

    csv_list = sorted(glob.glob("data/logs_*.csv"), reverse=True)
    if csv_list:
        selected = st.selectbox("Ventana:", csv_list,
                                format_func=lambda x: x.replace("data/logs_","").replace(".csv",""))
        df_sel = pd.read_csv(selected)

        col_tipo, col_app = st.columns(2)
        with col_tipo:
            tipos = ["Todos"] + sorted(df_sel["sap_function_log_type"].dropna().unique().tolist())
            tipo_sel = st.selectbox("Tipo de log:", tipos)
        with col_app:
            if "sap_function_application" in df_sel.columns:
                apps = ["Todas"] + sorted(df_sel["sap_function_application"].dropna().unique().tolist())
                app_sel = st.selectbox("Aplicación SAP:", apps)
            else:
                app_sel = "Todas"

        if tipo_sel != "Todos":
            df_sel = df_sel[df_sel["sap_function_log_type"] == tipo_sel]
        if app_sel != "Todas":
            df_sel = df_sel[df_sel["sap_function_application"] == app_sel]

        st.markdown(f'<div class="label-mono" style="margin-bottom:6px;">{len(df_sel)} registros</div>',
                    unsafe_allow_html=True)
        st.dataframe(df_sel, use_container_width=True, height=300, hide_index=True)
    else:
        st.info("Sin CSVs disponibles.")

# TAB DE ATAQUE
def show_attack_tab(df_all, alerts_df, date_str, label, description, card_css):
    df_day = df_all[df_all["_window"].str.startswith(date_str)].copy()

    st.markdown(f"""
    <div class="attack-card {card_css}">
        <div style="font-family:'Playfair Display',serif;font-weight:700;
                    font-size:1.1rem;color:#1a1025;">{label}</div>
        <div style="font-family:'DM Mono',monospace;font-size:0.65rem;
                    color:#9b8ab4;margin-top:4px;">{description}</div>
    </div>
    """, unsafe_allow_html=True)

    if df_day.empty:
        st.warning(f"Sin datos CSV para {label}.")
        return

    total      = len(df_day)
    errors     = len(df_day[df_day["sap_function_log_type"].isin(["ERROR","LLM_ERROR","LLM_TIMEOUT","SECURITY"])])
    llm_req    = len(df_day[df_day["sap_function_log_type"]=="LLM_REQUEST"])
    error_rate = errors / total * 100 if total > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registros totales", f"{total:,}")
    c2.metric("Eventos de error",  f"{errors:,}")
    c3.metric("Tasa de error",     f"{error_rate:.1f}%")
    c4.metric("Requests LLM",      f"{llm_req:,}")

    st.markdown('<div class="label-mono" style="margin:14px 0 6px;">Evolución de eventos críticos durante el ataque</div>',
                unsafe_allow_html=True)

    log_all = ["LLM_ERROR","LLM_TIMEOUT","SECURITY","ERROR","WARNING","LLM_REQUEST"]
    pivot = (
        df_day[df_day["sap_function_log_type"].isin(log_all)]
        .groupby(["_window","sap_function_log_type"])
        .size().unstack(fill_value=0).sort_index()
    )
    pivot.index = [w[9:13]+":"+w[13:15] for w in pivot.index]
    st.line_chart(pivot, height=250)

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown('<div class="label-mono" style="margin-bottom:8px;">Alertas enviadas</div>',
                    unsafe_allow_html=True)
        if alerts_df is not None and not alerts_df.empty and "timestamp_utc" in alerts_df.columns:
            day_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            mask = alerts_df["timestamp_utc"].astype(str).str.startswith(day_fmt)
            if "window_start" in alerts_df.columns:
                mask = mask | alerts_df["window_start"].astype(str).str.startswith(day_fmt)
            day_alerts = alerts_df[mask].copy()
            if not day_alerts.empty:
                high   = len(day_alerts[day_alerts["severity"]=="HIGH"])
                medium = len(day_alerts[day_alerts["severity"]=="MEDIUM"])
                a1, a2, a3 = st.columns(3)
                a1.metric("Total", len(day_alerts))
                a2.metric("HIGH",   high)
                a3.metric("MEDIUM", medium)
                cols_show = [c for c in ["timestamp_utc","severity","alert_type","message"]
                             if c in day_alerts.columns]
                st.dataframe(day_alerts[cols_show].sort_values("timestamp_utc", ascending=False),
                             use_container_width=True, height=250, hide_index=True)
            else:
                st.info("Sin alertas registradas para este día.")
        else:
            st.info("Carga la fuente de datos para ver alertas por día.")

    with col_right:
        st.markdown('<div class="label-mono" style="margin-bottom:8px;">Errores por aplicación SAP</div>',
                    unsafe_allow_html=True)
        if "sap_function_application" in df_day.columns:
            app_errors = (
                df_day[df_day["sap_function_log_type"].isin(["ERROR","LLM_ERROR","LLM_TIMEOUT","SECURITY"])]
                .groupby("sap_function_application").size()
                .sort_values(ascending=False).head(10)
            )
            st.bar_chart(app_errors, height=250, color="#7c3aed")


# TABS ATAQUES
with tab_ataques:
    st.markdown('<div class="section-title">Ataques detectados durante el hackathon</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="label-mono" style="margin-bottom:20px;">3 ataques identificados · MTTD promedio 2.6 segundos</div>',
                unsafe_allow_html=True)

    show_attack_tab(df_all, alerts_df, "20260504",
                    "4 de Mayo 2026", "LLM_ERROR Spike — z-score 21.5",
                    "attack-card-red")

    show_attack_tab(df_all, alerts_df, "20260506",
                    "6 de Mayo 2026", "Intensidad Máxima — z-score 25.5",
                    "attack-card-orange")

    show_attack_tab(df_all, alerts_df, "20260511",
                    "11 de Mayo 2026", "9 Aplicaciones Simultáneas — LLM_REQUEST z=54.1",
                    "attack-card-purple")

# TAB BASELINE
with tab_baseline:
    st.markdown('<div class="section-title">Umbrales dinámicos del detector</div>', unsafe_allow_html=True)
    st.markdown('<div class="label-mono" style="margin-bottom:16px;">Calculados con MAD robusto · /baseline</div>',
                unsafe_allow_html=True)

    baseline = api_get_baseline()

    if "error" in baseline:
        st.warning(f"No se pudo cargar el baseline: {baseline['error']}")
        st.info("Asegúrate de que la FastAPI esté corriendo en localhost:8000.")
    else:
        updated = baseline.get("updated_at", "")
        if updated:
            st.markdown(f'<div class="label-mono">Última actualización: {updated[:19]} UTC</div>',
                        unsafe_allow_html=True)
            st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)

        thresholds = baseline.get("thresholds", {})
        if thresholds:
            rows = []
            for log_type, vals in thresholds.items():
                rows.append({
                    "Tipo de log":     log_type,
                    "Mediana (hist.)": round(vals.get("median", vals.get("mean", 0)), 1),
                    "MAD":             round(vals.get("mad",    vals.get("std",  0)), 1),
                    "Umbral (3.5s)":   round(vals.get("threshold", 0), 1),
                })
            df_bl = pd.DataFrame(rows).sort_values("Umbral (3.5s)", ascending=False)
            st.dataframe(df_bl, use_container_width=True, hide_index=True, height=320)

            st.markdown('<div class="label-mono" style="margin:16px 0 8px;">Comparativa mediana vs umbral</div>',
                        unsafe_allow_html=True)
            chart_data = df_bl.set_index("Tipo de log")[["Mediana (hist.)","Umbral (3.5s)"]]
            st.bar_chart(chart_data, height=260, color=["#c4b5fd","#7c3aed"])
        else:
            st.info("Baseline vacío. Corre el pipeline al menos 5 ventanas para generarlo.")

# TAB ASISTENTE NOVA
with tab_chat:
    st.markdown('<div class="section-title">Asistente NOVA</div>', unsafe_allow_html=True)
    st.markdown('<div class="label-mono" style="margin-bottom:16px;">Consulta el sistema en lenguaje natural · powered by Gemini</div>',
                unsafe_allow_html=True)

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    suggestions = [
        "¿Qué pasó el 4 de mayo?",
        "¿Por qué se disparó la alerta de LLM?",
        "¿Cuántas alertas HIGH hubo?",
        "¿Qué aplicaciones SAP fueron afectadas?",
        "¿Cuál fue el MTTD promedio?",
        "¿El sistema está detectando ataques ahora?",
    ]

    st.markdown('<div class="label-mono" style="margin-bottom:8px;">Preguntas sugeridas</div>',
                unsafe_allow_html=True)
    sugg_cols = st.columns(3)
    for i, s in enumerate(suggestions):
        with sugg_cols[i % 3]:
            if st.button(s, key=f"sugg_{i}", use_container_width=True):
                #st.session_state["chat_input"] = s
                #st.rerun()
                st.session_state["pending_question"] = s

    st.markdown("<hr style='margin:14px 0'>", unsafe_allow_html=True)

    question = st.text_input(
        "Tu pregunta:",
        value=st.session_state.get("pending_question", ""),
        placeholder="Escribe tu pregunta aquí...",
        key="chat_input"
    )
    if "pending_question" in st.session_state:
        del st.session_state["pending_question"]

    sc1, sc2 = st.columns([3, 1])
    with sc1:
        send = st.button("Enviar", use_container_width=True)
    with sc2:
        if st.button("Limpiar", use_container_width=True):
            st.session_state.chat_history = []
            #st.rerun()

    if send and question.strip():
        with st.spinner("NOVA está analizando..."):
            response = api_chat(question.strip())
        st.session_state.chat_history.append({
            "q":   question.strip(),
            "a":   response.get("answer", "Sin respuesta").strip(),
            "ts":  datetime.utcnow().strftime("%H:%M:%S"),
            "ctx": response.get("context_alerts", 0),
        })
        #st.rerun()

    for entry in reversed(st.session_state.chat_history):
        answer_html = entry['a'].replace('\n', '<br>')
        st.markdown(f"""
        <div style="margin-bottom:18px;">
            <div style="background:#f8f7fc;border:1px solid #ede8f5;
                        border-radius:12px 12px 12px 2px;padding:12px 18px;margin-bottom:6px;">
                <div style="font-family:'DM Mono',monospace;font-size:0.6rem;
                            color:#9b8ab4;margin-bottom:4px;">TÚ · {entry['ts']} UTC</div>
                <div style="color:#1a1025;font-size:0.9rem;">{entry['q']}</div>
            </div>
            <div style="background:#ffffff;border:1px solid #ede8f5;border-left:3px solid #7c3aed;
                        border-radius:2px 12px 12px 12px;padding:14px 18px;
                        box-shadow:0 1px 4px rgba(124,58,237,0.06);">
                <div style="font-family:'DM Mono',monospace;font-size:0.6rem;
                            color:#7c3aed;margin-bottom:6px;">
                    NOVA · {entry['ctx']} alertas en contexto
                </div>
                <div style="color:#1a1025;font-size:0.9rem;line-height:1.6;">
                {answer_html}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    if not st.session_state.chat_history:
        st.markdown("""
        <div style="text-align:center;padding:50px 20px;">
            <div style="font-family:'Playfair Display',serif;font-size:1.5rem;
                        color:#c4b5fd;margin-bottom:12px;">NOVA</div>
            <div style="font-family:'DM Mono',monospace;font-size:0.7rem;
                        color:#9b8ab4;line-height:1.8;">
                El asistente está listo.<br>
                Haz una pregunta sobre el sistema de detección.
            </div>
        </div>
        """, unsafe_allow_html=True)


# Auto-refresh 
if auto_refresh:
    time.sleep(refresh_interval)
    st.cache_data.clear()
    st.rerun()