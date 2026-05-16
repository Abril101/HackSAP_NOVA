import streamlit as st
import pandas as pd
import glob
import os
import requests
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TOKEN   = os.getenv("SAP_TOKEN")
BASE    = os.getenv("SAP_BASE_URL")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

st.set_page_config(page_title="NOVA — SAP SOC", layout="wide")
st.title("NOVA — SAP Security Operations Center")

# ── HANA data loader ─────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_from_hana():
    try:
        from hana import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT window_id, log_type, application, http_status_code, client_ip, llm_cost_usd, llm_response_time_ms, llm_provider, region FROM SAP_LOGS")
        rows = cursor.fetchall()
        cols = ["_window", "sap_function_log_type", "sap_function_application",
                "http_status_code", "client_ip", "llm_cost_usd", "llm_response_time_ms",
                "llm_provider", "region"]
        cursor.close()
        conn.close()
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
        cursor.execute("SELECT timestamp_utc, alert_type, severity, message, status_code, window_start, response_ms FROM SAP_ALERTS ORDER BY created_at DESC")
        rows = cursor.fetchall()
        cols = ["timestamp_utc", "alert_type", "severity", "message", "status_code", "window_start", "response_ms"]
        cursor.close()
        conn.close()
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
        tmp["_window"] = os.path.basename(f).replace("logs_", "").replace(".csv", "")
        dfs.append(tmp)
    return pd.concat(dfs, ignore_index=True)


def fmt_time(ms):
    if pd.isna(ms):
        return "—"
    ms = int(ms)
    return f"{ms//60000}m {(ms%60000)//1000}s {ms%1000}ms"


def show_attack_tab(df_all, alerts_df, date_str, label, description, color):
    """Renders content for a single attack tab."""
    df_day = df_all[df_all["_window"].str.startswith(date_str)].copy()

    if df_day.empty:
        st.warning(f"No hay datos para {label}.")
        return

    st.markdown(f"### {label} — {description}")

    # ── Métricas del día ──────────────────────────────────────────
    total = len(df_day)
    errors = len(df_day[df_day["sap_function_log_type"].isin(["ERROR", "LLM_ERROR", "LLM_TIMEOUT", "SECURITY"])])
    llm_req = len(df_day[df_day["sap_function_log_type"] == "LLM_REQUEST"])
    error_rate = errors / total * 100 if total > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registros totales", f"{total:,}")
    c2.metric("Eventos de error", f"{errors:,}")
    c3.metric("Tasa de error", f"{error_rate:.1f}%")
    c4.metric("Requests LLM", f"{llm_req:,}")

    # ── Gráfica de tendencia del día ──────────────────────────────
    st.markdown("**Evolución de eventos críticos durante el ataque**")
    log_types_criticos = ["LLM_ERROR", "LLM_TIMEOUT", "SECURITY", "ERROR", "WARNING", "LLM_REQUEST"]
    pivot = (
        df_day[df_day["sap_function_log_type"].isin(log_types_criticos)]
        .groupby(["_window", "sap_function_log_type"])
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )
    pivot.index = [w[9:13] + ":" + w[13:15] for w in pivot.index]
    st.line_chart(pivot, height=250)

    col_left, col_right = st.columns(2)

    # ── Alertas del día ───────────────────────────────────────────
    with col_left:
        st.markdown("**Alertas enviadas**")
        if alerts_df is not None and not alerts_df.empty:
            day_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            day_alerts = alerts_df[alerts_df["timestamp_utc"].str.startswith(day_fmt)].copy()
            if not day_alerts.empty:
                high   = len(day_alerts[day_alerts["severity"] == "HIGH"])
                medium = len(day_alerts[day_alerts["severity"] == "MEDIUM"])
                a1, a2, a3 = st.columns(3)
                a1.metric("Total", len(day_alerts))
                a2.metric("HIGH", high)
                a3.metric("MEDIUM", medium)
                cols_show = ["timestamp_utc", "severity", "alert_type", "message"]
                cols_show = [c for c in cols_show if c in day_alerts.columns]
                st.dataframe(day_alerts[cols_show].sort_values("timestamp_utc", ascending=False),
                             use_container_width=True, height=250, hide_index=True)
            else:
                st.info("No hay alertas registradas en el CSV para este día.")
        else:
            st.info("Carga la fuente CSV para ver alertas por día.")

    # ── Distribución por aplicación ───────────────────────────────
    with col_right:
        st.markdown("**Errores por aplicación SAP**")
        if "sap_function_application" in df_day.columns:
            app_errors = (
                df_day[df_day["sap_function_log_type"].isin(["ERROR", "LLM_ERROR", "LLM_TIMEOUT", "SECURITY"])]
                .groupby("sap_function_application")
                .size()
                .sort_values(ascending=False)
                .head(10)
            )
            st.bar_chart(app_errors, height=250)


# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.header("Configuración")
    data_source = st.radio("Fuente de datos", ["HANA Cloud", "CSV local"], index=1)
    st.divider()
    auto_refresh = st.toggle("Auto-refresh", value=False)
    refresh_interval = st.selectbox("Intervalo", [30, 60, 120], index=1, format_func=lambda x: f"{x}s")
    st.divider()
    st.caption(f"Última actualización:\n{datetime.utcnow().strftime('%H:%M:%S')} UTC")
    if st.button("Actualizar ahora"):
        st.rerun()

# ── Estado en vivo ────────────────────────────────────────────────
st.subheader("Estado en vivo")
c1, c2, c3, c4 = st.columns(4)

try:
    health = requests.get(f"{BASE}/health", timeout=5).json()
    c1.metric("Servidor", "OK" if health.get("status") == "ok" else "DOWN")
except:
    c1.metric("Servidor", "SIN CONEXIÓN")

try:
    info = requests.get(f"{BASE}/info", headers=HEADERS, timeout=5).json()
    c2.metric("Registros (ventana actual)", f"{info.get('total_records', 0):,}")
    c3.metric("Ventana", f"{info.get('window_start','?')[11:16]} → {info.get('window_end','?')[11:16]} UTC")
except:
    c2.metric("Registros", "—")
    c3.metric("Ventana", "—")

# ── Cargar datos ──────────────────────────────────────────────────
if data_source == "HANA Cloud":
    df_all = load_from_hana()
    n_windows = df_all["_window"].nunique() if not df_all.empty else 0
    c4.metric("Ventanas en HANA ☁", n_windows)
else:
    csv_files = sorted(glob.glob("data/logs_*.csv"))
    df_all = load_all_csv()
    c4.metric("Ventanas capturadas", len(csv_files))

if df_all.empty:
    st.warning("No hay datos aún. Corre pipeline.py.")
    st.stop()

# ── Cargar alertas ────────────────────────────────────────────────
if data_source == "HANA Cloud":
    alerts_df = load_alerts_from_hana()
else:
    alert_path = "data/alerts_log.csv"
    alerts_df = pd.read_csv(alert_path, on_bad_lines="skip") if os.path.exists(alert_path) else pd.DataFrame()

st.divider()

# ── TABS ──────────────────────────────────────────────────────────
tab_general, tab_atk1, tab_atk2, tab_atk3 = st.tabs([
    "Vista General",
    "Ataque 4-May — LLM Error Spike",
    "Ataque 6-May — Intensidad Máxima",
    "Ataque 11-May — 9 Apps Simultáneas",
])

# ── Tab General ───────────────────────────────────────────────────
with tab_general:
    st.subheader("Tendencias históricas — todas las ventanas")
    log_types_criticos = ["LLM_ERROR", "LLM_TIMEOUT", "SECURITY", "ERROR", "WARNING"]
    pivot = (
        df_all[df_all["sap_function_log_type"].isin(log_types_criticos)]
        .groupby(["_window", "sap_function_log_type"])
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )
    pivot.index = [w[9:13] + ":" + w[13:15] for w in pivot.index]
    st.line_chart(pivot, height=280)
    st.caption("Conteo por tipo de log en cada ventana de 30 min capturada")

    st.divider()
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Historial de alertas enviadas")
        if alerts_df is not None and not alerts_df.empty:
            alerts_sorted = alerts_df.sort_values("timestamp_utc", ascending=False)
            total  = len(alerts_sorted)
            high   = len(alerts_sorted[alerts_sorted["severity"] == "HIGH"])
            medium = len(alerts_sorted[alerts_sorted["severity"] == "MEDIUM"])

            if "response_ms" in alerts_sorted.columns:
                valid_times = alerts_sorted["response_ms"].dropna()
                avg_ms = valid_times.mean()
                min_ms = valid_times.min()

                a1, a2, a3, a4 = st.columns(4)
                a1.metric("Total alertas", total)
                a2.metric("HIGH", high)
                a3.metric("MEDIUM", medium)
                a4.metric("MTTD promedio", fmt_time(avg_ms))
                st.caption(f"MTTD mínimo: {fmt_time(min_ms)}")
            else:
                a1, a2, a3 = st.columns(3)
                a1.metric("Total alertas", total)
                a2.metric("HIGH", high)
                a3.metric("MEDIUM", medium)

            cols_show = ["timestamp_utc", "severity", "alert_type", "message"]
            cols_show = [c for c in cols_show if c in alerts_sorted.columns]
            st.dataframe(alerts_sorted[cols_show], use_container_width=True, height=300,
                         column_config={"timestamp_utc": "Hora UTC", "severity": "Severidad",
                                        "alert_type": "Tipo", "message": "Mensaje"})
        else:
            st.info("No hay alertas registradas.")

    with col_right:
        st.subheader("Análisis LLM")
        llm_df = df_all[df_all["sap_function_log_type"].isin(["LLM_REQUEST", "LLM_ERROR", "LLM_TIMEOUT"])].copy()
        llm_df["llm_cost_usd"] = pd.to_numeric(llm_df.get("llm_cost_usd"), errors="coerce")
        llm_df["llm_response_time_ms"] = pd.to_numeric(llm_df.get("llm_response_time_ms"), errors="coerce")

        total_llm  = len(llm_df)
        llm_errors = len(llm_df[llm_df["sap_function_log_type"].isin(["LLM_ERROR", "LLM_TIMEOUT"])])
        error_rate = llm_errors / total_llm * 100 if total_llm > 0 else 0
        avg_cost   = llm_df["llm_cost_usd"].mean()
        max_cost   = llm_df["llm_cost_usd"].max()

        b1, b2, b3 = st.columns(3)
        b1.metric("Tasa de error LLM", f"{error_rate:.1f}%")
        b2.metric("Costo promedio", f"${avg_cost:.4f}")
        b3.metric("Costo máximo", f"${max_cost:.4f}")

        cost_by_window = (
            llm_df[llm_df["sap_function_log_type"] == "LLM_REQUEST"]
            .groupby("_window")["llm_cost_usd"].mean().sort_index()
        )
        cost_by_window.index = [w[9:13] + ":" + w[13:15] for w in cost_by_window.index]
        st.caption("Costo LLM promedio por ventana")
        st.line_chart(cost_by_window, height=150)

    st.divider()
    st.subheader("Explorar logs por ventana")
    if data_source == "HANA Cloud":
        available_windows = sorted(df_all["_window"].dropna().unique().tolist(), reverse=True)
        selected_window = st.selectbox("Ventana:", available_windows)
        df_sel = df_all[df_all["_window"] == selected_window].copy()
    else:
        csv_list = sorted(glob.glob("data/logs_*.csv"), reverse=True)
        selected = st.selectbox("Ventana:", csv_list,
                                format_func=lambda x: x.replace("data/logs_", "").replace(".csv", ""))
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

    st.caption(f"{len(df_sel)} registros")
    st.dataframe(df_sel, use_container_width=True, height=300)

# ── Tab Ataque 4-May ──────────────────────────────────────────────
with tab_atk1:
    show_attack_tab(df_all, alerts_df, "20260504",
                    "4 de Mayo 2026",
                    "LLM_ERROR Spike — z-score 21.5",
                    "red")

# ── Tab Ataque 6-May ──────────────────────────────────────────────
with tab_atk2:
    show_attack_tab(df_all, alerts_df, "20260506",
                    "6 de Mayo 2026",
                    "Intensidad Máxima — z-score 25.5",
                    "orange")

# ── Tab Ataque 11-May ─────────────────────────────────────────────
with tab_atk3:
    show_attack_tab(df_all, alerts_df, "20260511",
                    "11 de Mayo 2026",
                    "9 Aplicaciones Simultáneas — LLM_REQUEST z=54.1",
                    "purple")

# ── Auto-refresh ──────────────────────────────────────────────────
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()
