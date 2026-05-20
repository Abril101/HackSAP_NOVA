import pandas as pd
import numpy as np
import requests
import os
import glob
import json
from datetime import datetime, timezone
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler, LabelEncoder
from dotenv import load_dotenv

load_dotenv()

TOKEN   = os.getenv("SAP_TOKEN")
BASE    = os.getenv("SAP_BASE_URL")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


# ============================================================================
# CARGA DE DATOS
# ============================================================================

def load_latest_csv():
    files = sorted(glob.glob("data/logs_*.csv"), reverse=True)
    if not files:
        print("No hay CSVs en /data. Corre pipeline.py primero.")
        return None
    df = pd.read_csv(files[0])
    print(f"Cargado: {files[0]} ({len(df)} filas)")
    return df


def load_historical(n=10, exclude_attack_windows=True):
    """
    Carga las ultimas n ventanas historicas (excluye la actual).

    NUEVO: por default excluye ventanas que ya generaron alertas confirmadas.
    Esto previene que el modelo aprenda los ataques como comportamiento normal
    (concept drift). Si exclude_attack_windows=False, carga todas.
    """
    files = sorted(glob.glob("data/logs_*.csv"))
    if len(files) <= 1:
        return None

    historical_files = files[:-1]  # excluir la mas reciente (ventana actual)

    # Filtrar ventanas que tuvieron alertas previas
    attack_windows = set()
    if exclude_attack_windows:
        attack_windows = load_attack_windows()
        if attack_windows:
            print(f"  Excluyendo {len(attack_windows)} ventanas con alertas previas del historial")

    # Tomar las ultimas n ventanas LIMPIAS
    clean_files = []
    for f in reversed(historical_files):
        window_id = os.path.basename(f).replace("logs_", "").replace(".csv", "")
        if window_id not in attack_windows:
            clean_files.append(f)
        if len(clean_files) >= n:
            break

    clean_files = list(reversed(clean_files))

    # Si quedaron muy pocas ventanas limpias, usar las que sea para no quedarnos sin baseline
    if len(clean_files) < 3:
        print(f"  Solo {len(clean_files)} ventanas limpias. Usando las ultimas {n} sin filtrar.")
        clean_files = historical_files[-n:]

    dfs = []
    for f in clean_files:
        tmp = pd.read_csv(f)
        tmp["_window"] = os.path.basename(f).replace("logs_", "").replace(".csv", "")
        dfs.append(tmp)
    hist = pd.concat(dfs, ignore_index=True)
    print(f"  Historial: {len(clean_files)} ventanas cargadas ({len(hist)} registros)")
    return hist


def load_attack_windows():
    """Lee data/alerts_log.csv y devuelve set de ventanas que tuvieron alertas."""
    log_path = "data/alerts_log.csv"
    if not os.path.exists(log_path):
        return set()
    try:
        alerts = pd.read_csv(log_path)
        if "window_start" not in alerts.columns:
            return set()
        windows = set()
        for ts in alerts["window_start"].dropna().unique():
            try:
                dt = pd.to_datetime(ts)
                window_id = dt.strftime("%Y%m%d_%H%M")
                windows.add(window_id)
            except Exception:
                continue
        return windows
    except Exception as e:
        print(f"  Error leyendo alerts_log: {e}")
        return set()


# ============================================================================
# PREPROCESAMIENTO
# ============================================================================

def preprocess(df):
    df = df.copy()
    llm_types = ["LLM_REQUEST", "LLM_ERROR", "LLM_TIMEOUT"]

    df["is_llm"] = df["sap_function_log_type"].isin(llm_types).astype(int)

    le = LabelEncoder()
    df["log_type_enc"] = le.fit_transform(df["sap_function_log_type"].fillna("UNKNOWN"))

    df["http_status_code"]     = pd.to_numeric(df.get("http_status_code"), errors="coerce").fillna(-1)
    df["llm_cost_usd"]         = pd.to_numeric(df.get("llm_cost_usd"), errors="coerce").fillna(0)
    df["llm_response_time_ms"] = pd.to_numeric(df.get("llm_response_time_ms"), errors="coerce").fillna(0)

    if "client_ip" in df.columns:
        le_ip = LabelEncoder()
        df["client_ip_enc"] = le_ip.fit_transform(df["client_ip"].fillna("unknown"))
    else:
        df["client_ip_enc"] = 0

    if "llm_provider" in df.columns:
        le_prov = LabelEncoder()
        df["llm_provider_enc"] = le_prov.fit_transform(df["llm_provider"].fillna("unknown"))
    else:
        df["llm_provider_enc"] = 0

    return df


# ============================================================================
# ESTADISTICAS ROBUSTAS (MAD en vez de std)
# ============================================================================

def robust_stats(series):
    """
    Calcula mediana y MAD (Median Absolute Deviation).
    MAD es resistente a outliers, std clasico no.

    Devuelve: (median, mad_scaled). El mad_scaled equivale a std en
    una distribucion normal, asi se puede comparar con umbrales tipo sigma.
    """
    arr = np.asarray(series, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return 0.0, 0.0

    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))

    if mad == 0:
        q75, q25 = np.percentile(arr, [75, 25])
        iqr = q75 - q25
        mad_scaled = iqr / 1.349
    else:
        mad_scaled = mad * 1.4826

    return med, mad_scaled


def robust_zscore(value, median, mad_scaled):
    """Z-score robusto: cuantos MAD-equivalentes esta lejos de la mediana."""
    if mad_scaled == 0:
        return 0.0
    return (value - median) / mad_scaled


BASELINE_PATH = "data/baseline_cache.json"
MIN_WINDOWS_TO_UPDATE = 5


def save_baseline(thresholds):
    serializable = {k: {kk: float(vv) for kk, vv in v.items()} for k, v in thresholds.items()}
    with open(BASELINE_PATH, "w") as f:
        json.dump({"updated_at": datetime.now(timezone.utc).isoformat(), "thresholds": serializable}, f)


def load_baseline_cache():
    if not os.path.exists(BASELINE_PATH):
        return {}
    try:
        with open(BASELINE_PATH) as f:
            data = json.load(f)
        print(f"  Baseline cargado desde cache ({data.get('updated_at','?')[:10]})")
        return data.get("thresholds", {})
    except Exception:
        return {}


# ============================================================================
# UMBRALES DINAMICOS (con MAD robusto)
# ============================================================================

def compute_dynamic_thresholds(historical_df, threshold_mad=3.5):
    thresholds = {}
    if historical_df is None or "_window" not in historical_df.columns:
        cached = load_baseline_cache()
        if cached:
            print("  Sin historial suficiente. Usando baseline cacheado.")
            return cached
        return thresholds

    n_windows = historical_df["_window"].nunique()
    if n_windows < MIN_WINDOWS_TO_UPDATE:
        cached = load_baseline_cache()
        if cached:
            print(f"  Solo {n_windows} ventanas en historial. Usando baseline cacheado.")
            return cached

    counts_per_window = (
        historical_df.groupby(["_window", "sap_function_log_type"])
        .size()
        .unstack(fill_value=0)
    )

    for log_type in counts_per_window.columns:
        series = counts_per_window[log_type].values
        med, mad = robust_stats(series)
        if mad == 0:
            continue
        thresholds[log_type] = {
            "mean": med,
            "std":  mad,
            "median": med,
            "mad":  mad,
            "threshold": med + threshold_mad * mad
        }

    if "LLM_ERROR" in counts_per_window.columns and "LLM_TIMEOUT" in counts_per_window.columns:
        combined = (counts_per_window["LLM_ERROR"] + counts_per_window["LLM_TIMEOUT"]).values
        med, mad = robust_stats(combined)
        if mad > 0:
            thresholds["LLM_COMBINED"] = {
                "mean": med, "std": mad,
                "median": med, "mad": mad,
                "threshold": med + threshold_mad * mad
            }

    llm_req = historical_df[historical_df["sap_function_log_type"] == "LLM_REQUEST"].copy()
    llm_req["llm_cost_usd"] = pd.to_numeric(llm_req["llm_cost_usd"], errors="coerce")
    if len(llm_req) > 0:
        cost_per_window = llm_req[llm_req["llm_cost_usd"] > 0.032].groupby("_window").size()
        if len(cost_per_window) > 0:
            med, mad = robust_stats(cost_per_window.values)
            if mad > 0:
                thresholds["LLM_COST_COUNT"] = {
                    "mean": med, "std": mad,
                    "median": med, "mad": mad,
                    "threshold": med + threshold_mad * mad
                }

    save_baseline(thresholds)
    print(f"  Baseline robusto (MAD) actualizado con {n_windows} ventanas y guardado.")
    return thresholds


# ============================================================================
# UMBRALES POR HORA DEL DIA (estacionalidad)
# ============================================================================

def compute_hourly_thresholds(historical_df, threshold_mad=3.5):
    if historical_df is None or "_window" not in historical_df.columns:
        return {}

    df = historical_df.copy()
    df["_hour"] = df["_window"].str[9:11].astype(int)

    hourly_thresholds = {}

    for hour in range(24):
        hour_data = df[df["_hour"] == hour]
        if hour_data["_window"].nunique() < 3:
            continue

        counts = hour_data.groupby(["_window", "sap_function_log_type"]).size().unstack(fill_value=0)

        for log_type in counts.columns:
            series = counts[log_type].values
            med, mad = robust_stats(series)
            if mad == 0:
                continue
            hourly_thresholds[(hour, log_type)] = {
                "median": med,
                "mad": mad,
                "threshold": med + threshold_mad * mad,
                "n_samples": len(series)
            }

    return hourly_thresholds


# ============================================================================
# REGLAS CON UMBRALES ROBUSTOS
# ============================================================================

def apply_rules(df, historical_df=None, current_window=None):
    """
    Retorna (hard_alerts, soft_signals).

    hard_alerts: señales de seguridad directa — se envían como alerta.
      - credential_theft: fuerza bruta 401/403 por IP
      - security_spike:   spike de eventos SECURITY sobre baseline

    soft_signals: señales operacionales — NO se envían solas, solo
    contribuyen al sistema de corroboración del Isolation Forest.
      - llm_abuse:        LLM_ERROR/TIMEOUT anómalos (puede ser bug o proveedor lento)
      - llm_cost_anomaly: costo LLM alto (puede ser uso legítimo intenso)

    Separar ambas categorías permite al modelo mantener generalidad
    sin generar ruido en ventanas operacionalmente ruidosas pero seguras.
    """
    hard_alerts  = []
    soft_signals = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    thresholds = compute_dynamic_thresholds(historical_df)
    hourly = compute_hourly_thresholds(historical_df) if historical_df is not None else {}

    current_hour = None
    if current_window and len(current_window) >= 11:
        try:
            current_hour = int(current_window[9:11])
        except Exception:
            pass

    def get_threshold(key, fallback):
        if current_hour is not None and (current_hour, key) in hourly:
            h = hourly[(current_hour, key)]
            return h["threshold"], h["median"]
        if key in thresholds and not np.isnan(thresholds[key]["threshold"]):
            return thresholds[key]["threshold"], thresholds[key].get("median", thresholds[key]["mean"])
        return fallback, None

    # Regla 1: Robo de credenciales — alerta directa (intrusión confirmada)
    if "client_ip" in df.columns and "http_status_code" in df.columns:
        auth_fails = df[df["http_status_code"].isin([401, 403])]
        ip_counts  = auth_fails["client_ip"].value_counts()
        bad_ips    = ip_counts[ip_counts >= 10]
        for ip, count in bad_ips.items():
            ts = df[df["client_ip"] == ip]["@timestamp"].iloc[0] if "@timestamp" in df.columns else timestamp
            hard_alerts.append({
                "type": "credential_theft", "severity": "HIGH",
                "message": f"WHAT: Brute-force login attempt. WHEN: {ts[:19]}Z. WHY: {count} HTTP 401/403 from IP {ip} in current window."
            })

    # Regla 2: Spike de SECURITY — alerta directa (eventos de seguridad confirmados)
    if "sap_function_log_type" in df.columns:
        counts = df["sap_function_log_type"].value_counts()
        for log_type, fallback in {"SECURITY": 105, "ERROR": 514}.items():
            thr, med = get_threshold(log_type, fallback)
            count = counts.get(log_type, 0)
            if count > thr:
                baseline_str = f"hist median={med:.0f}" if med else f"fallback={fallback}"
                hard_alerts.append({
                    "type": "security_spike", "severity": "HIGH",
                    "message": f"WHAT: {log_type} spike above robust baseline. WHEN: {timestamp}. WHY: {count} events ({baseline_str}, threshold={thr:.0f})."
                })

    # Regla 3: LLM abuse — señal suave (puede ser bug o proveedor lento, no intrusión directa)
    llm_err = df[df["sap_function_log_type"].isin(["LLM_ERROR", "LLM_TIMEOUT"])]
    thr_llm, med_llm = get_threshold("LLM_COMBINED", 724)
    if len(llm_err) > thr_llm:
        baseline_str = f"hist median={med_llm:.0f}" if med_llm else "fallback=724"
        soft_signals.append({
            "type": "llm_abuse", "severity": "MEDIUM",
            "message": f"WHAT: Abnormal LLM error rate. WHEN: {timestamp}. WHY: {len(llm_err)} LLM_ERROR/TIMEOUT events ({baseline_str}, threshold={thr_llm:.0f})."
        })

    # Regla 4: LLM cost — señal suave (puede ser uso legítimo intenso)
    if "llm_cost_usd" in df.columns:
        llm_req   = df[df["sap_function_log_type"] == "LLM_REQUEST"].copy()
        llm_req["llm_cost_usd"] = pd.to_numeric(llm_req["llm_cost_usd"], errors="coerce")
        expensive = llm_req[llm_req["llm_cost_usd"] > 0.032]
        thr_cost, med_cost = get_threshold("LLM_COST_COUNT", 213)
        if len(expensive) > thr_cost:
            top_cost = expensive["llm_cost_usd"].max()
            baseline_str = f"hist median={med_cost:.0f}" if med_cost else "fallback=213"
            soft_signals.append({
                "type": "llm_cost_anomaly", "severity": "MEDIUM",
                "message": f"WHAT: Abnormal LLM cost detected. WHEN: {timestamp}. WHY: {len(expensive)} costly requests ({baseline_str}, threshold={thr_cost:.0f}, max=${top_cost:.4f})."
            })

    return hard_alerts, soft_signals


# ============================================================================
# Z-SCORE HISTORICO (robust con MAD)
# ============================================================================

def zscore_comparison(current_df, historical_df):
    """
    Umbrales subidos a 5.0 (MEDIUM) y 7.0 (HIGH) para reducir falsos positivos.
    Solo devuelve 1 alerta: la del tipo con mayor z-score.
    En días normales z-scores son 1-3; los ataques reales mostraron z=7.5-54.
    """
    if historical_df is None or "_window" not in historical_df.columns:
        print("  Sin historial suficiente para z-score.")
        return []

    log_types  = ["LLM_ERROR", "LLM_TIMEOUT", "SECURITY", "ERROR", "WARNING", "LLM_REQUEST"]
    hist_pivot = historical_df.groupby(["_window", "sap_function_log_type"]).size().unstack(fill_value=0)
    current_counts = current_df["sap_function_log_type"].value_counts()

    best_alert = None
    best_z     = 0.0

    for log_type in log_types:
        if log_type not in hist_pivot.columns:
            continue
        hist_series = hist_pivot[log_type].values
        med, mad = robust_stats(hist_series)
        current = current_counts.get(log_type, 0)

        if mad == 0:
            continue

        rz = robust_zscore(current, med, mad)
        print(f"  [robust z] {log_type}: {current} actual vs {med:.0f} hist (rz={rz:.1f})")

        if rz > 5.0 and rz > best_z:
            best_z    = rz
            severity  = "HIGH" if rz > 7.0 else "MEDIUM"
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            best_alert = {
                "type": "historical_anomaly", "severity": severity,
                "message": f"WHAT: {log_type} anomaly vs {len(hist_series)}-window robust baseline. WHEN: {timestamp}. WHY: {current} events (hist median={med:.0f}, robust_z={rz:.1f})."
            }

    if best_alert:
        print(f"  → Alerta z-score: {best_alert['message'][:80]}...")
        return [best_alert]

    print("  Sin anomalias historicas detectadas (umbral z=5.0).")
    return []


# ============================================================================
# DETECCION POR APLICACION (robust)
# ============================================================================

def check_per_application(current_df, historical_df):
    """
    Solo envía alerta si ≥3 apps superan el umbral simultáneamente.
    Un ataque focalizado en 1-2 apps puede ser ruido; ≥3 apps simultáneas
    indica ataque coordinado automatizado — señal mucho más confiable.
    Devuelve 1 alerta consolidada listando todas las apps afectadas.
    """
    if historical_df is None or "sap_function_application" not in current_df.columns:
        print("  Sin historial para analisis por aplicacion.")
        return []

    error_types = ["ERROR", "LLM_ERROR", "LLM_TIMEOUT", "SECURITY"]

    hist_errors    = historical_df[historical_df["sap_function_log_type"].isin(error_types)]
    hist_by_app    = hist_errors.groupby(["_window", "sap_function_application"]).size().unstack(fill_value=0)
    curr_errors    = current_df[current_df["sap_function_log_type"].isin(error_types)]
    current_by_app = curr_errors.groupby("sap_function_application").size()

    fired_apps = []
    for app in current_by_app.index:
        if app not in hist_by_app.columns:
            continue
        hist_series = hist_by_app[app].values
        med, mad = robust_stats(hist_series)
        current = current_by_app[app]

        if mad == 0:
            continue

        rz = robust_zscore(current, med, mad)
        if rz > 3.0:
            severity = "HIGH" if rz > 3.5 else "MEDIUM"
            fired_apps.append({"app": app, "count": current, "med": med, "rz": rz, "severity": severity})
            print(f"  [app robust z] {app}: {current} vs {med:.0f} hist (rz={rz:.1f})")

    if len(fired_apps) < 3:
        n = len(fired_apps)
        msg = f"  {n} app(s) con anomalia — necesita ≥3 para alerta (ataque coordinado)." if n > 0 else "  Sin anomalias por aplicacion."
        print(msg)
        return []

    # ≥3 apps afectadas: ataque coordinado confirmado
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    severity  = "HIGH" if any(a["severity"] == "HIGH" for a in fired_apps) else "MEDIUM"
    top_apps  = sorted(fired_apps, key=lambda x: -x["rz"])[:5]
    apps_summary = ", ".join(f"{a['app']}(z={a['rz']:.1f})" for a in top_apps)
    suffix = f" +{len(fired_apps)-5} more" if len(fired_apps) > 5 else ""

    return [{
        "type": "app_anomaly", "severity": severity,
        "message": f"WHAT: Coordinated error spike across {len(fired_apps)} SAP apps. WHEN: {timestamp}. WHY: {apps_summary}{suffix}."
    }]


# ============================================================================
# ISOLATION FOREST
# ============================================================================

def run_isolation_forest(current_df, historical_df=None):
    features  = ["log_type_enc", "http_status_code", "llm_response_time_ms",
                 "client_ip_enc", "is_llm", "llm_provider_enc"]

    curr_proc = preprocess(current_df)
    available = [f for f in features if f in curr_proc.columns]

    if historical_df is not None and len(historical_df) >= 500:
        hist_proc = preprocess(historical_df)
        hist_avail = [f for f in available if f in hist_proc.columns]
        X_train = hist_proc[hist_avail].fillna(0)
        X_test  = curr_proc[hist_avail].fillna(0)
        model = IsolationForest(contamination=0.05, random_state=42)
        model.fit(X_train)
        curr_proc = curr_proc.copy()
        curr_proc["anomaly_score"] = model.predict(X_test)
        print(f"  IF entrenado sobre {len(X_train)} registros historicos")
    else:
        X_test = curr_proc[available].fillna(0)
        model  = IsolationForest(contamination=0.05, random_state=42)
        curr_proc = curr_proc.copy()
        curr_proc["anomaly_score"] = model.fit_predict(X_test)
        print("  IF entrenado sobre ventana actual (sin historial suficiente)")

    curr_proc["anomaly"] = curr_proc["anomaly_score"] == -1
    n = curr_proc["anomaly"].sum()
    print(f"  Isolation Forest: {n} anomalias de {len(curr_proc)} registros")

    return curr_proc


# ============================================================================
# ONE-CLASS SVM NOVELTY DETECTION (nueva capa)
# ============================================================================

def run_oneclass_svm_novelty(current_df, historical_df):
    """
    One-Class SVM entrenado solo con datos historicos limpios.
    nu=0.01 detecta eventos extremadamente raros (<1%).
    """
    alerts = []

    if historical_df is None or len(historical_df) < 500:
        print("  OCSVM: historial insuficiente, saltando.")
        return alerts

    features = ["log_type_enc", "http_status_code", "llm_response_time_ms",
                "client_ip_enc", "is_llm", "llm_provider_enc"]

    try:
        hist_proc = preprocess(historical_df)
        curr_proc = preprocess(current_df)
        avail = [f for f in features if f in hist_proc.columns and f in curr_proc.columns]

        if len(hist_proc) > 5000:
            hist_sample = hist_proc.sample(n=5000, random_state=42)
        else:
            hist_sample = hist_proc

        X_train = hist_sample[avail].fillna(0).values
        X_test  = curr_proc[avail].fillna(0).values

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s  = scaler.transform(X_test)

        model = OneClassSVM(kernel="rbf", gamma="scale", nu=0.01)
        model.fit(X_train_s)
        predictions = model.predict(X_test_s)

        novelties = predictions == -1
        n_novelties = int(novelties.sum())

        print(f"  OCSVM novelty: {n_novelties} registros raros de {len(predictions)}")

        if n_novelties >= 5:
            curr_proc = curr_proc.copy()
            curr_proc["is_novelty"] = novelties
            suspicious_types = ["SECURITY", "ERROR", "LLM_ERROR", "LLM_TIMEOUT"]
            susp_novelties = curr_proc[
                (curr_proc["is_novelty"]) &
                (curr_proc["sap_function_log_type"].isin(suspicious_types))
            ]

            if len(susp_novelties) >= 3:
                breakdown = susp_novelties["sap_function_log_type"].value_counts().to_dict()
                summary = ", ".join(f"{k}:{v}" for k, v in breakdown.items())
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                alerts.append({
                    "type": "ocsvm_novelty",
                    "severity": "HIGH" if len(susp_novelties) >= 10 else "MEDIUM",
                    "message": f"WHAT: Rare pattern detected by novelty detector (OCSVM). WHEN: {timestamp}. WHY: {len(susp_novelties)} suspicious novel records ({summary})."
                })
    except Exception as e:
        print(f"  OCSVM error: {e}")

    return alerts


# ============================================================================
# ENVIO DE ALERTA
# ============================================================================

try:
    from hana import insert_alert as hana_insert_alert
    HANA_ENABLED = True
except Exception:
    HANA_ENABLED = False


'''def send_alert(message: str, alert_type: str = "unknown", severity: str = "MEDIUM", window_start: str = None, fetch_time=None):
    if len(message) > 300:
        message = message[:297] + "..."
    r = requests.post(f"{BASE}/alert", headers=HEADERS, json={"message": message})
    status = r.status_code
    alert_time = datetime.now(timezone.utc)

    if status == 201:
        print(f"  ALERTA ENVIADA: {r.json()}")
    else:
        print(f"  Error enviando alerta: {status} - {r.text}")

    response_ms = None
    if fetch_time:
        try:
            response_ms = int((alert_time - fetch_time).total_seconds() * 1000)
            mins = response_ms // 60000
            secs = (response_ms % 60000) // 1000
            ms   = response_ms % 1000
            print(f"  Tiempo de procesamiento: {mins}m {secs}s {ms}ms desde recepcion de datos")
        except Exception:
            pass

    timestamp_str = alert_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    log_row = pd.DataFrame([{
        "timestamp_utc": timestamp_str,
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "status_code": status,
        "window_start": window_start,
        "response_ms": response_ms
    }])
    log_path = "data/alerts_log.csv"
    if os.path.exists(log_path):
        log_row.to_csv(log_path, mode="a", header=False, index=False)
    else:
        log_row.to_csv(log_path, index=False)

    if HANA_ENABLED:
        try:
            hana_insert_alert(timestamp_str, alert_type, severity, message, status, window_start, response_ms)
        except Exception as e:
            print(f"  HANA insert_alert error: {e}")

    return status
'''

# ============================================================================
# PIPELINE COMPLETO
# ============================================================================

def run_detection(df, window_start: str = None, fetch_time=None):
    print(f"\n[{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC] Corriendo deteccion...")
    if window_start:
        print(f"  Ventana: {window_start}")

    historical_df = load_historical(n=10, exclude_attack_windows=True)
    df_proc = preprocess(df)

    current_window_id = None
    if window_start:
        try:
            current_window_id = pd.to_datetime(window_start).strftime("%Y%m%d_%H%M")
        except Exception:
            pass

    # 1. Reglas — separa alertas directas (security) de señales suaves (llm operacional)
    print("\n-- Reglas con umbrales robustos (MAD) --")
    rule_alerts, soft_signals = apply_rules(df_proc, historical_df, current_window=current_window_id)
    if rule_alerts:
        for alert in rule_alerts:
            print(f"  [{alert['severity']}] {alert['type']}: {alert['message'][:80]}...")
            send_alert(alert["message"], alert["type"], alert["severity"], window_start, fetch_time)
    else:
        print("  Sin alertas de seguridad directa.")
    if soft_signals:
        print(f"  Señales suaves (solo corroboración): {[s['type'] for s in soft_signals]}")

    # 2. Robust z-score historico (umbral 5.0 — 1 alerta máximo, la de mayor z)
    print("\n-- Robust z-score historico --")
    zscore_alerts = zscore_comparison(df, historical_df)
    for alert in zscore_alerts:
        print(f"  [{alert['severity']}] {alert['type']}: {alert['message'][:80]}...")
        send_alert(alert["message"], alert["type"], alert["severity"], window_start, fetch_time)

    # 3. Anomalias por aplicacion (≥3 apps simultáneas — 1 alerta consolidada)
    print("\n-- Deteccion por aplicacion --")
    app_alerts = check_per_application(df, historical_df)
    for alert in app_alerts:
        print(f"  [{alert['severity']}] {alert['type']}: {alert['message'][:80]}...")
        send_alert(alert["message"], alert["type"], alert["severity"], window_start, fetch_time)

    ocsvm_alerts = []

    # 4. Isolation Forest (corroboración: incluye soft_signals como señal adicional)
    print("\n-- Isolation Forest --")
    df_proc = run_isolation_forest(df, historical_df)

    if "anomaly" in df_proc.columns:
        anomalies = df_proc[df_proc["anomaly"] == True]
        if len(anomalies) > 0:
            print(f"  Tipos anomalos:\n{anomalies['sap_function_log_type'].value_counts().to_string()}")
            suspicious = ["SECURITY", "ERROR", "LLM_ERROR", "LLM_TIMEOUT"]
            susp_count = anomalies[anomalies["sap_function_log_type"].isin(suspicious)]
            other_layers_fired = (
                len(rule_alerts) > 0 or
                len(zscore_alerts) > 0 or
                len(app_alerts) > 0 or
                len(ocsvm_alerts) > 0 or
                len(soft_signals) > 0  # señales suaves también corroboran
            )
            if len(susp_count) >= 10 and other_layers_fired:
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                breakdown = anomalies["sap_function_log_type"].value_counts().to_dict()
                summary   = ", ".join(f"{k}:{v}" for k, v in breakdown.items() if k in suspicious)
                send_alert(
                    f"WHAT: Anomaly cluster detected by ML model. WHEN: {timestamp}. "
                    f"WHY: {len(anomalies)} anomalous records - {summary}.",
                    "isolation_forest", "MEDIUM", window_start, fetch_time
                )
            elif len(susp_count) >= 10:
                print(f"  IF detecto {len(susp_count)} sospechosos pero ninguna otra capa confirmo. Sin alerta.")

    return df_proc


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    df = load_latest_csv()
    if df is not None:
        run_detection(df)
