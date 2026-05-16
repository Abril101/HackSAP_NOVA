# Análisis Exploratorio de Datos (EDA)
## Hack IDM x SAP — Live Security Operations Center Defense
**Equipo:** NOVA  
**Fecha:** 30 de abril de 2026  
**Autor:** Abril Álvarez Mercado

---

## 1. Objetivo

Caracterizar el comportamiento normal del sistema SAP a partir de los logs de producción capturados en tiempo real, con el fin de:

- Establecer un **baseline estadístico** por tipo de evento
- **Calibrar los umbrales** del sistema de detección de anomalías
- Identificar patrones de interés para el modelo de Machine Learning

---

## 2. Fuente de Datos

Los datos fueron obtenidos directamente de la API del hackathon mediante un pipeline de ingesta en tiempo real (`pipeline.py`). Se recopilaron **12 ventanas de 30 minutos** correspondientes al día 30 de abril de 2026.

| Métrica | Valor |
|---|---|
| Total de registros | 63,909 |
| Número de ventanas | 12 |
| Promedio de logs por ventana | ~5,326 |
| Total de columnas | 45 |
| Período cubierto | 14:59 – 23:15 UTC |

El dataset se construyó concatenando todos los archivos CSV generados por el pipeline, agregando una columna `_window` para identificar la ventana de origen de cada registro.

---

## 3. Estructura del Dataset

Los logs contienen dos tipos de registros con estructuras distintas:

**Logs de sistema** — campos activos: `http_status_code`, `client_ip`, `sap_function_application`, `headers_http_request_method`, `region_name`

**Logs LLM** — campos activos: `llm_model_id`, `llm_provider`, `llm_cost_usd`, `llm_response_time_ms`, `llm_prompt_tokens`, `llm_completion_tokens`, `llm_total_tokens`, `llm_status`, `llm_error_message`

Esta separación genera un patrón de nulos estructurado: los campos LLM tienen ~60% de nulos (corresponden a logs de sistema) y viceversa. Los nulos **no son datos faltantes** — son la consecuencia natural de la naturaleza mixta del dataset.

### Columnas con nulos relevantes

| Columna | % Nulos | Razón |
|---|---|---|
| `_ignored` | 100% | Columna vacía de Elasticsearch, se descarta |
| Columnas `llm_*` | ~60% | Solo aplican a logs LLM |
| `http_status_code`, `client_ip` | ~40% | Solo aplican a logs de sistema |
| `llm_error_message` | 88.2% | Solo presente en LLM_ERROR |

---

## 4. Distribución de Tipos de Log

Se identificaron 10 tipos de log (`sap_function_log_type`), divididos en dos grupos:

### Distribución global

| Tipo | Count | % |
|---|---|---|
| LLM_REQUEST | 17,924 | 28.05% |
| INFO | 14,439 | 22.59% |
| WARNING | 6,992 | 10.94% |
| ERROR | 5,364 | 8.39% |
| LLM_ERROR | 5,059 | 7.92% |
| DEBUG | 3,738 | 5.85% |
| AUDIT | 3,485 | 5.45% |
| PERF | 3,406 | 5.33% |
| LLM_TIMEOUT | 2,488 | 3.89% |
| SECURITY | 1,014 | 1.59% |

**Hallazgo:** La distribución es estable entre ventanas — las proporciones no varían significativamente de una ventana a otra, lo que confirma que existe un comportamiento de referencia bien definido.

---

## 5. Análisis de HTTP Status Codes

Se analizaron únicamente los logs de sistema (excluidos logs LLM).

### Distribución de códigos

| Código | Descripción | Count |
|---|---|---|
| 200 | OK | 20,989 |
| 201 | Created | 2,678 |
| 204 | No Content | 2,541 |
| 400 | Bad Request | 1,770 |
| 500 | Internal Server Error | 1,613 |
| 429 | Too Many Requests | 1,416 |
| 302 | Redirect | 1,381 |
| 408 | Request Timeout | 1,354 |
| 403 | Forbidden | 534 |
| 401 | Unauthorized | 531 |

### Análisis de errores de autenticación (401/403)

- **Total 401/403:** 1,065 registros (1.7% del total)
- **Promedio por ventana:** 89 eventos
- **Top IP con más 401/403:** `88.72.40.56` con 23 eventos en 12 ventanas

Ninguna IP superó 23 errores de autenticación en el período completo analizado. El umbral de ≥10 por ventana para activar la alerta `credential_theft` se considera adecuado y conservador.

---

## 6. Análisis de IPs

Las IPs más frecuentes presentan una distribución relativamente uniforme (~390–492 requests), lo que sugiere comportamiento de múltiples servicios o clientes sin dominancia anómala.

| IP | Requests totales |
|---|---|
| 220.141.26.13 | 492 |
| 119.64.224.237 | 466 |
| 36.109.47.72 | 452 |
| 20.114.207.221 | 427 |

Se observan IPs del rango `192.168.x.x` (red interna) entre las más activas, lo que es consistente con tráfico interno de microservicios SAP.

---

## 7. Análisis de Variables LLM

### Estadísticas descriptivas

| Variable | Media | Std | Min | Max |
|---|---|---|---|---|
| `llm_cost_usd` | $0.0126 | $0.0192 | $0.0000 | $0.1364 |
| `llm_response_time_ms` | 8,761 ms | 8,639 ms | 200 ms | 34,999 ms |
| `llm_prompt_tokens` | 1,026 | 564 | 50 | 2,000 |
| `llm_completion_tokens` | 769 | 425 | 30 | 1,500 |
| `llm_total_tokens` | 1,795 | 707 | 93 | 3,495 |

### Outliers detectados (método IQR)

| Variable | Outliers | % |
|---|---|---|
| `llm_cost_usd` | 2,734 | 10.7% |
| `llm_response_time_ms` | 2,488 | 9.8% |
| `llm_prompt_tokens` | 0 | 0% |
| `llm_completion_tokens` | 0 | 0% |
| `llm_total_tokens` | 0 | 0% |

**Hallazgo clave:** Los tokens no presentan outliers — el uso de tokens es predecible. Sin embargo, el costo y el tiempo de respuesta sí tienen outliers significativos (~10%), lo que los convierte en variables relevantes para detectar uso anormal del LLM.

El umbral de costo para alerta se fijó en **>$0.032 USD** (Q3 + 1.5×IQR).

---

## 8. Análisis Temporal — LLM_ERROR + LLM_TIMEOUT por ventana

| Ventana | LLM_ERROR + LLM_TIMEOUT |
|---|---|
| 20260430_1459 | 608 |
| 20260430_1527 | 658 |
| 20260430_1603 | 600 |
| 20260430_1922 | 609 |
| 20260430_2028 | 611 |
| 20260430_2030 | 686 |
| 20260430_2039 | 686 |
| 20260430_2100 | 637 |
| 20260430_2130 | 608 |
| 20260430_2133 | 608 |
| 20260430_2233 | 634 |
| 20260430_2315 | 602 |

- **Media:** 629 eventos/ventana
- **Desviación estándar:** 32
- **Umbral 3-sigma:** 724

**Hallazgo crítico:** El detector original disparaba alerta con ≥5 LLM_ERROR/TIMEOUT — un umbral completamente incorrecto dado que el baseline real es ~629. Esto generaba un **falso positivo garantizado en cada ventana**. El umbral fue corregido a 724.

---

## 9. Baseline por Tipo de Log (umbrales 3-sigma)

| Tipo de log | Media/ventana | Std | Umbral de alerta (3σ) |
|---|---|---|---|
| LLM_REQUEST | 1,494 | 45 | 1,630 |
| INFO | 1,203 | 44 | 1,335 |
| WARNING | 583 | 22 | 650 |
| ERROR | 447 | 22 | **514** |
| LLM_ERROR | 422 | 24 | 495 |
| DEBUG | 312 | 23 | 380 |
| AUDIT | 290 | 16 | 339 |
| PERF | 284 | 15 | 330 |
| LLM_TIMEOUT | 207 | 15 | **251** |
| SECURITY | 84 | 7 | **105** |

---

## 10. Contexto Adicional

| Variable | Hallazgo |
|---|---|
| Aplicaciones SAP | 10 aplicaciones con distribución uniforme (~6,300-6,555 logs c/u) |
| Entornos | sandbox, staging, qa, development, production — distribución equilibrada |
| Regiones | North America (31.6%), Europe (30.6%), Asia (18.3%), MEA (13.9%) |
| HTTP methods | GET, POST, PUT, DELETE, PATCH presentes |

---

## 11. Ajustes Aplicados al Sistema de Detección

Con base en los hallazgos del EDA, se actualizaron las reglas del detector (`detector.py`):

| Regla | Antes | Después |
|---|---|---|
| `llm_abuse` | ≥5 LLM_ERROR/TIMEOUT | >724 (3-sigma) |
| `security_spike` ERROR | >30% del total | >514 (3-sigma) |
| `security_spike` SECURITY | >30% del total | >105 (3-sigma) |
| `llm_cost_anomaly` | No existía | >5 requests con costo >$0.032 |
| `credential_theft` | ≥10 por IP | Sin cambio (válido) |

---

## 12. Conclusiones

1. El dataset presenta un comportamiento **estable y predecible** entre ventanas, lo que permite establecer un baseline confiable con solo 12 muestras.
2. Los logs LLM y de sistema son **estructuralmente distintos** y deben tratarse por separado en el preprocesamiento.
3. Las variables más sensibles para detección de anomalías son: `llm_cost_usd`, `llm_response_time_ms`, `http_status_code` (401/403), y los conteos de `SECURITY` y `LLM_TIMEOUT`.
4. El sistema de detección quedó calibrado con umbrales estadísticamente fundamentados, eliminando los falsos positivos de la versión inicial.

---

*Código del EDA disponible en: `eda.py`*  
*Gráficas generadas en: `eda_output/`*
