import pandas as pd
import numpy as np
import glob
import os

files = sorted(glob.glob("data/logs_*.csv"))
dfs = []
for f in files:
    tmp = pd.read_csv(f)
    tmp["_window"] = os.path.basename(f).replace("logs_", "").replace(".csv", "")
    dfs.append(tmp)

df = pd.concat(dfs, ignore_index=True)
print(f"Total: {len(df):,} registros | {df['_window'].nunique()} ventanas\n")

error_types = ["ERROR", "LLM_ERROR", "LLM_TIMEOUT", "SECURITY"]
errors = df[df["sap_function_log_type"].isin(error_types)]

# ── 1. Errores por aplicación SAP ────────────────────────────────
print("=" * 55)
print("1. ERRORES POR APLICACIÓN SAP")
print("=" * 55)
app_errors = errors.groupby(["sap_function_application", "sap_function_log_type"]).size().unstack(fill_value=0)
app_errors["TOTAL"] = app_errors.sum(axis=1)
app_errors = app_errors.sort_values("TOTAL", ascending=False)
print(app_errors.to_string())

app_total = df.groupby("sap_function_application").size().rename("total_logs")
app_errors["total_logs"] = app_total
app_errors["pct_error"] = (app_errors["TOTAL"] / app_errors["total_logs"] * 100).round(1)
print(f"\nTasa de error por app:")
print(app_errors[["TOTAL", "total_logs", "pct_error"]].sort_values("pct_error", ascending=False).to_string())

# ── 2. IPs más frecuentes en errores 401/403 ─────────────────────
print("\n" + "=" * 55)
print("2. IPs SOSPECHOSAS (401/403)")
print("=" * 55)
if "http_status_code" in df.columns and "client_ip" in df.columns:
    auth_fails = df[df["http_status_code"].isin([401, 403])]
    ip_per_window = auth_fails.groupby(["client_ip", "_window"]).size().unstack(fill_value=0)
    ip_max = ip_per_window.max(axis=1).sort_values(ascending=False).head(15)
    ip_total = auth_fails["client_ip"].value_counts().head(15)
    print(f"\nTop 15 IPs por total de 401/403:")
    print(ip_total.to_string())
    print(f"\nMáximo 401/403 en una sola ventana (por IP):")
    print(ip_max.to_string())
    print(f"\nUmbral actual de alerta: ≥10 por ventana")
    print(f"IPs que lo superarían: {(ip_max >= 10).sum()}")

# ── 3. Análisis por región ────────────────────────────────────────
print("\n" + "=" * 55)
print("3. ERRORES POR REGIÓN")
print("=" * 55)
if "macro_region" in df.columns:
    region_errors = errors.groupby("macro_region").size().sort_values(ascending=False)
    region_total  = df.groupby("macro_region").size()
    region_df = pd.DataFrame({"errores": region_errors, "total": region_total})
    region_df["pct"] = (region_df["errores"] / region_df["total"] * 100).round(1)
    print(region_df.sort_values("pct", ascending=False).to_string())

# ── 4. Análisis por proveedor LLM ─────────────────────────────────
print("\n" + "=" * 55)
print("4. ERRORES POR PROVEEDOR LLM")
print("=" * 55)
if "llm_provider" in df.columns:
    llm_logs = df[df["sap_function_log_type"].isin(["LLM_REQUEST", "LLM_ERROR", "LLM_TIMEOUT"])]
    prov_counts = llm_logs.groupby(["llm_provider", "sap_function_log_type"]).size().unstack(fill_value=0)
    prov_counts["ERROR_RATE"] = (
        (prov_counts.get("LLM_ERROR", 0) + prov_counts.get("LLM_TIMEOUT", 0)) /
        prov_counts.sum(axis=1) * 100
    ).round(1)
    print(prov_counts.sort_values("ERROR_RATE", ascending=False).to_string())

# ── 5. HTTP methods con más errores ──────────────────────────────
print("\n" + "=" * 55)
print("5. HTTP METHODS CON MÁS ERRORES 4xx/5xx")
print("=" * 55)
if "headers_http_request_method" in df.columns:
    http_errors = df[df["http_status_code"] >= 400]
    method_err = http_errors.groupby("headers_http_request_method").size().sort_values(ascending=False)
    method_total = df.groupby("headers_http_request_method").size()
    method_df = pd.DataFrame({"errores": method_err, "total": method_total})
    method_df["pct"] = (method_df["errores"] / method_df["total"] * 100).round(1)
    print(method_df.sort_values("pct", ascending=False).to_string())

# ── 6. Correlaciones útiles para el modelo ───────────────────────
print("\n" + "=" * 55)
print("6. CORRELACIONES PARA EL MODELO")
print("=" * 55)
df["is_error"] = df["sap_function_log_type"].isin(error_types).astype(int)
df["http_status_code"] = pd.to_numeric(df["http_status_code"], errors="coerce")
df["llm_cost_usd"] = pd.to_numeric(df["llm_cost_usd"], errors="coerce")
df["llm_response_time_ms"] = pd.to_numeric(df["llm_response_time_ms"], errors="coerce")

num_cols = ["is_error", "http_status_code", "llm_cost_usd", "llm_response_time_ms"]
corr = df[num_cols].corr()["is_error"].drop("is_error").sort_values(key=abs, ascending=False)
print("\nCorrelación con 'es_error':")
print(corr.to_string())

print("\n" + "=" * 55)
print("RESUMEN PARA AJUSTAR EL MODELO")
print("=" * 55)
