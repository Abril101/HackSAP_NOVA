import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import glob
import os
from datetime import datetime

sns.set_theme(style="darkgrid")
os.makedirs("eda_output", exist_ok=True)

# ── 1. CARGA DE DATOS ────────────────────────────────────────────────────────

files = sorted(glob.glob("data/logs_*.csv"))
print(f"Archivos encontrados: {len(files)}")
for f in files:
    print(f"  {f}")

dfs = []
for f in files:
    tmp = pd.read_csv(f)
    tmp["_window"] = os.path.basename(f).replace("logs_", "").replace(".csv", "")
    dfs.append(tmp)

df = pd.concat(dfs, ignore_index=True)
print(f"\nDataset combinado: {df.shape[0]} filas, {df.shape[1]} columnas")
print(f"Ventanas cargadas: {df['_window'].nunique()}")

# ── 2. DESCRIPCIÓN BÁSICA ────────────────────────────────────────────────────

print("\n── Tipos de datos ──")
print(df.dtypes.to_string())

print("\n── Primeras 3 filas ──")
print(df.head(3).to_string())

# ── 3. NULOS ─────────────────────────────────────────────────────────────────

print("\n── Valores nulos por columna ──")
nulls = df.isnull().sum()
nulls_pct = (nulls / len(df) * 100).round(1)
null_report = pd.DataFrame({"nulos": nulls, "pct": nulls_pct})
print(null_report[null_report["nulos"] > 0].to_string())

# ── 4. DISTRIBUCIÓN DE TIPOS DE LOG ─────────────────────────────────────────

print("\n── Distribución global de sap_function_log_type ──")
log_counts = df["sap_function_log_type"].value_counts()
log_pct    = (log_counts / len(df) * 100).round(2)
print(pd.DataFrame({"count": log_counts, "pct%": log_pct}).to_string())

fig, ax = plt.subplots(figsize=(10, 5))
log_counts.plot(kind="bar", ax=ax, color="steelblue")
ax.set_title("Distribución de tipos de log (todas las ventanas)")
ax.set_ylabel("Cantidad")
ax.set_xlabel("")
plt.xticks(rotation=30, ha="right")
plt.tight_layout()
plt.savefig("eda_output/01_log_type_dist.png", dpi=150)
plt.close()
print("  → eda_output/01_log_type_dist.png")

# Distribución por ventana (¿es estable?)
pivot_window = df.groupby(["_window", "sap_function_log_type"]).size().unstack(fill_value=0)
fig, ax = plt.subplots(figsize=(12, 5))
pivot_window.plot(kind="bar", stacked=True, ax=ax, colormap="tab10")
ax.set_title("Tipos de log por ventana (estabilidad temporal)")
ax.set_ylabel("Cantidad")
ax.set_xlabel("Ventana")
plt.xticks(rotation=30, ha="right")
plt.legend(loc="upper right", fontsize=7)
plt.tight_layout()
plt.savefig("eda_output/02_log_type_by_window.png", dpi=150)
plt.close()
print("  → eda_output/02_log_type_by_window.png")

# ── 5. HTTP STATUS CODES ─────────────────────────────────────────────────────

print("\n── HTTP Status Codes ──")
sys_logs = df[df["sap_function_log_type"].isin(["INFO","WARNING","ERROR","DEBUG","AUDIT","PERF","SECURITY"])]
http_counts = sys_logs["http_status_code"].value_counts().head(20)
print(http_counts.to_string())

auth_fails = sys_logs[sys_logs["http_status_code"].isin([401, 403])]
print(f"\n  401/403 totales: {len(auth_fails)} ({len(auth_fails)/len(df)*100:.1f}% del total)")
print(f"  401/403 por ventana (promedio): {len(auth_fails)/df['_window'].nunique():.0f}")

if len(auth_fails) > 0 and "client_ip" in auth_fails.columns:
    top_fail_ips = auth_fails["client_ip"].value_counts().head(10)
    print(f"\n  Top IPs con 401/403:\n{top_fail_ips.to_string()}")

fig, ax = plt.subplots(figsize=(10, 5))
http_counts.plot(kind="bar", ax=ax, color="coral")
ax.set_title("Distribución de HTTP Status Codes (logs de sistema)")
ax.set_ylabel("Cantidad")
plt.xticks(rotation=0)
plt.tight_layout()
plt.savefig("eda_output/03_http_status.png", dpi=150)
plt.close()
print("  → eda_output/03_http_status.png")

# ── 6. ANÁLISIS DE IPs ───────────────────────────────────────────────────────

print("\n── Top 20 IPs más frecuentes ──")
if "client_ip" in df.columns:
    top_ips = df["client_ip"].value_counts().head(20)
    print(top_ips.to_string())

    fig, ax = plt.subplots(figsize=(10, 5))
    top_ips.plot(kind="bar", ax=ax, color="mediumpurple")
    ax.set_title("Top 20 IPs más frecuentes")
    ax.set_ylabel("Requests")
    plt.xticks(rotation=45, ha="right", fontsize=7)
    plt.tight_layout()
    plt.savefig("eda_output/04_top_ips.png", dpi=150)
    plt.close()
    print("  → eda_output/04_top_ips.png")

# ── 7. ANÁLISIS LLM ──────────────────────────────────────────────────────────

llm_logs = df[df["sap_function_log_type"].isin(["LLM_REQUEST","LLM_ERROR","LLM_TIMEOUT"])]
print(f"\n── LLM logs: {len(llm_logs)} ({len(llm_logs)/len(df)*100:.1f}% del total) ──")
print(f"  LLM_ERROR:   {len(df[df['sap_function_log_type']=='LLM_ERROR'])}")
print(f"  LLM_TIMEOUT: {len(df[df['sap_function_log_type']=='LLM_TIMEOUT'])}")
print(f"  LLM_REQUEST: {len(df[df['sap_function_log_type']=='LLM_REQUEST'])}")

llm_num_cols = ["llm_cost_usd", "llm_response_time_ms", "llm_prompt_tokens",
                "llm_completion_tokens", "llm_total_tokens"]
available_llm = [c for c in llm_num_cols if c in llm_logs.columns]

if available_llm:
    print(f"\n── Estadísticas LLM ──")
    print(llm_logs[available_llm].describe().round(4).to_string())

    for col in available_llm:
        series = llm_logs[col].dropna()
        if len(series) == 0:
            continue
        Q1, Q3 = series.quantile(0.25), series.quantile(0.75)
        IQR = Q3 - Q1
        outliers = series[(series < Q1 - 1.5*IQR) | (series > Q3 + 1.5*IQR)]
        print(f"  Outliers en {col}: {len(outliers)} ({len(outliers)/len(series)*100:.1f}%)")

    fig, axes = plt.subplots(1, len(available_llm), figsize=(5*len(available_llm), 4))
    if len(available_llm) == 1:
        axes = [axes]
    for ax, col in zip(axes, available_llm):
        data = llm_logs[col].dropna()
        if len(data) > 0:
            ax.hist(data, bins=40, color="teal", edgecolor="white")
            ax.set_title(col, fontsize=9)
            ax.set_xlabel("")
    plt.suptitle("Distribuciones de variables LLM", fontsize=11)
    plt.tight_layout()
    plt.savefig("eda_output/05_llm_distributions.png", dpi=150)
    plt.close()
    print("  → eda_output/05_llm_distributions.png")

# ── 8. LLM ERROR/TIMEOUT POR VENTANA (calibrar umbral) ───────────────────────

print("\n── LLM_ERROR + LLM_TIMEOUT por ventana ──")
llm_err = df[df["sap_function_log_type"].isin(["LLM_ERROR","LLM_TIMEOUT"])]
llm_per_window = llm_err.groupby("_window").size()
print(llm_per_window.to_string())
print(f"\n  Media: {llm_per_window.mean():.0f}  |  Std: {llm_per_window.std():.0f}")
print(f"  Umbral 3-sigma para alerta: {llm_per_window.mean() + 3*llm_per_window.std():.0f}")

# ── 9. APLICACIONES Y SERVICIOS ──────────────────────────────────────────────

print("\n── Top aplicaciones SAP ──")
if "sap_function_application" in df.columns:
    print(df["sap_function_application"].value_counts().head(10).to_string())

print("\n── Entornos ──")
if "sap_app_env" in df.columns:
    print(df["sap_app_env"].value_counts().to_string())

print("\n── Regiones ──")
if "macro_region" in df.columns:
    print(df["macro_region"].value_counts().to_string())

# ── 10. CORRELACIÓN ──────────────────────────────────────────────────────────

num_cols = ["http_status_code", "llm_cost_usd", "llm_response_time_ms",
            "llm_prompt_tokens", "llm_completion_tokens", "llm_total_tokens"]
available_num = [c for c in num_cols if c in df.columns]

if len(available_num) >= 2:
    corr = df[available_num].corr()
    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", ax=ax, linewidths=0.5)
    ax.set_title("Correlación entre variables numéricas")
    plt.tight_layout()
    plt.savefig("eda_output/06_correlation.png", dpi=150)
    plt.close()
    print("\n  → eda_output/06_correlation.png")

# ── 11. RESUMEN PARA CALIBRAR REGLAS ────────────────────────────────────────

print("\n" + "="*60)
print("RESUMEN PARA CALIBRAR REGLAS DE DETECCIÓN")
print("="*60)

total_windows = df["_window"].nunique()
logs_per_window = len(df) / total_windows

print(f"\nPromedio de logs por ventana: {logs_per_window:.0f}")
print(f"Ventanas analizadas: {total_windows}")

for log_type in df["sap_function_log_type"].unique():
    subset = df[df["sap_function_log_type"] == log_type]
    per_window = subset.groupby("_window").size()
    print(f"\n  {log_type}:")
    print(f"    Media/ventana: {per_window.mean():.0f}  |  Std: {per_window.std():.0f}  |  Max: {per_window.max()}")
    print(f"    Umbral 3-sigma: {per_window.mean() + 3*per_window.std():.0f}")

print("\nEDA completo. Imágenes en eda_output/")
