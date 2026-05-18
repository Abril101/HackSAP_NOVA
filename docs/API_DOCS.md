# API Documentation — SAP SOC Log Ingestion API v1.0.0

> URL base: `https://sap-api-b1.679168.xyz`
> Swagger/Docs: `https://sap-api-b1.679168.xyz/docs`
> Autenticación: Bearer token en todos los endpoints excepto /health

---

## ¿Para qué sirve esta API?

Es la **fuente de datos del hackathon**. El servidor genera logs de seguridad continuamente y tú tienes que:
1. **Consumir** esos logs cada 30 minutos (`/logs/current`)
2. **Detectar** anomalías con ML
3. **Enviar una alerta** cuando encuentres una amenaza (`/alert`)

---

## Endpoints

### 1. `GET /logs/current` — El más importante
Devuelve todos los logs del ventana de 30 minutos activa.

**Cómo funciona el tiempo:**
| Minuto UTC del servidor | Ventana que devuelve |
|---|---|
| 00 – 29 | HH:00:00 → HH:30:00 |
| 30 – 59 | HH:30:00 → HH+1:00:00 |

**Paginación:** El servidor controla el tamaño de página. Tú solo mandas el número de página.

**Código de ingesta completo:**
```python
import requests
import pandas as pd

TOKEN   = "tu-api-key-aqui"
BASE    = "https://sap-api-b1.679168.xyz"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# Página 1 para saber cuántas páginas hay en total
r = requests.get(f"{BASE}/logs/current", headers=HEADERS, params={"page": 1})
payload = r.json()

all_records = payload["data"]
for page in range(2, payload["total_pages"] + 1):
    r = requests.get(f"{BASE}/logs/current", headers=HEADERS, params={"page": page})
    all_records.extend(r.json()["data"])

df = pd.DataFrame(all_records)
print(df.head())
print(f"Total registros: {len(df)}")
```

**Campos de respuesta importantes:**
| Campo | Qué es |
|---|---|
| `request_time_utc` | Cuándo hiciste la llamada |
| `window_start` / `window_end` | El rango de tiempo de los logs |
| `total_records` | Cuántos logs hay en total esta ventana |
| `total_pages` | Cuántas páginas necesitas pedir |
| `data` | El arreglo con los logs reales |

---

### 2. `GET /health` — Verificar que el servidor vive
```python
r = requests.get(f"{BASE}/health")
print(r.json())  # {"status": "ok"} si está vivo
```
Útil para saber si el servidor cayó antes de intentar ingestar.

---

### 3. `GET /info` — Info de la ventana actual
Devuelve el tamaño de lote y cuántas páginas hay SIN descargar los datos.
Úsalo antes de empezar la ingesta para saber qué tan grande es.

```python
r = requests.get(f"{BASE}/info", headers=HEADERS)
print(r.json())
# {"batch_size": N, "window_start": "...", "window_end": "...", "total_records": N, "total_pages": N}
```

---

### 4. `POST /alert` — Enviar alerta de amenaza ⚠️ CRÍTICO
Este es el endpoint que te evalúan. Se llama cuando tu modelo detecta una anomalía.

**El mensaje debe responder 3 preguntas obligatorias (máx 300 caracteres):**

| # | Pregunta | Ejemplo |
|---|---|---|
| 1 | ¿Qué pasó? | Brute-force login on SAP-ERP-01 |
| 2 | ¿Cuándo? | 2026-04-26T17:32:00Z |
| 3 | ¿Por qué se disparó? | 63 HTTP 401 from IP 192.168.4.22 in 4 min |

**Formato exacto:**
```
WHAT: Brute-force login on SAP-ERP-01. WHEN: 2026-04-26T17:32:00Z. WHY: 63 HTTP 401 from IP 192.168.4.22 within 4 min.
```

**Request:**
```python
alert_payload = {
    "message": "WHAT: Spike in SECURITY logs from IP 192.168.x.x. WHEN: 2026-04-30T01:00:00Z. WHY: Isolation Forest score -0.85, 63 HTTP 401 in 4 min."
}
r = requests.post(f"{BASE}/alert", headers=HEADERS, json=alert_payload)
print(r.json())  # response exitosa es código 201
```

**Response exitosa (código 201):**
```json
{
  "status": "alert received",
  "team_name": "tu-equipo",
  "message": "tu-mensaje",
  "timestamp_utc": "2026-04-30T01:00:00Z"
}
```

---

## Estructura de los logs

Hay dos categorías de logs. **Nunca mezclan sus campos** — cuando uno tiene datos, el otro tiene nulos (eso es por diseño, no es un error).

### Logs del Sistema
| Campo clave | Valores posibles |
|---|---|
| `sap_function_log_type` | `INFO` `WARNING` `ERROR` `DEBUG` `AUDIT` `PERF` `SECURITY` |
| `http_status_code` | 200, 401, 403, 500, etc. |
| `client_ip` | IP de quien hizo la llamada |
| `service_id` | Qué servicio SAP generó el log |
| `_id` | Identificador único del log |
| `@timestamp` | Timestamp del evento |

### Logs de LLM (Interacciones con modelos de lenguaje)
| Campo clave | Valores posibles |
|---|---|
| `sap_function_log_type` | `LLM_REQUEST` `LLM_ERROR` `LLM_TIMEOUT` |
| `llm_model_id` | Qué modelo se usó |
| `llm_status` | Estado de la llamada al LLM |
| `llm_cost_usd` | Costo en dólares |
| `llm_response_time_ms` | Tiempo de respuesta en ms |

### Regla de nulls (importante para el preprocessing)
```python
# Los logs de sistema tienen nulos en columnas LLM
# Los logs de LLM tienen nulos en columnas de sistema
# Hay que manejar esto antes de entrenar el modelo:

df_system = df[df["sap_function_log_type"].isin(["INFO","WARNING","ERROR","DEBUG","AUDIT","PERF","SECURITY"])]
df_llm    = df[df["sap_function_log_type"].isin(["LLM_REQUEST","LLM_ERROR","LLM_TIMEOUT"])]
```

---

## ¿Qué señales buscar? (para el modelo ML)

| Amenaza | Señal en los logs | Modelo |
|---|---|---|
| Robo de credenciales | Muchos `http_status_code` 401/403 desde el mismo `client_ip` | Isolation Forest |
| Pico de seguridad | Spike en logs de tipo `SECURITY` o `ERROR` | ARIMA / Prophet |
| Uso no autorizado de LLM | `LLM_ERROR` o `LLM_TIMEOUT` excesivos, o `llm_cost_usd` anormal | Isolation Forest |

---

## ¿Cómo usar los endpoints? (resumen del video de Santiago)

| Método | Cuándo usarlo |
|---|---|
| **Swagger UI** (`/docs`) | Para explorar y probar endpoints manualmente con "Try it out" |
| **cURL en terminal** | Llamada rápida sin abrir Python |
| **Python `requests`** | Para el pipeline automatizado (lo que vamos a construir) |
| **Bruno / Postman** | Para organizar y guardar colecciones de llamadas |

**cURL de prueba rápida:**
```bash
curl -H "Authorization: Bearer tu-api-key" https://sap-api-b1.679168.xyz/health
curl -H "Authorization: Bearer tu-api-key" https://sap-api-b1.679168.xyz/info
```
