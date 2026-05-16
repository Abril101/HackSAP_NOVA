# NOVA — Reporte Técnico de Arquitectura
## Live Security Operation Center Defense Hackathon
### Hack IDM x SAP, Mayo 2026

---

## 1. Descripción General

NOVA es un sistema de detección de amenazas en tiempo real diseñado para monitorear logs de SAP y enviar alertas automáticas ante comportamientos anómalos. Opera de forma continua con un ciclo de polling de 60 segundos y una arquitectura de detección multicapa no supervisada.

---

## 2. Componentes del Sistema

### 2.1 `pipeline.py` — Ingesta y Orquestación

Responsable de conectarse a la API SAP, descargar los logs de cada ventana de 30 minutos y coordinar el análisis.

**Flujo:**
1. Llama a `GET /info` para detectar si hay una ventana nueva disponible
2. Si la ventana es nueva, descarga todos los registros paginados (`GET /logs/current`, 500 registros/página)
3. Guarda los datos en CSV local (`data/logs_YYYYMMDD_HHMM.csv`)
4. Invoca `run_detection()` del detector para analizar la ventana
5. Hace polling cada 60 segundos — nunca analiza la misma ventana dos veces

**Decisiones de diseño:**
- Polling inteligente en lugar de cron: detecta nuevas ventanas en cuanto aparecen
- `analyzed_windows` como set en memoria: evita doble procesamiento sin necesidad de base de datos
- `HANA_ENABLED = False` por defecto: el sistema funciona sin HANA, usando CSV como fallback

---

### 2.2 `detector.py` — Motor de Detección (4 Capas)

Núcleo del sistema. Implementa cuatro capas de detección complementarias, cada una diseñada para detectar un tipo diferente de amenaza.

#### Capa 1: Reglas con Umbrales Dinámicos (MAD)

Detecta spikes absolutos en conteos de eventos por tipo de log.

- Calcula umbrales usando **MAD (Median Absolute Deviation)** con factor 1.4826, más robusto que la desviación estándar ante outliers
- Umbral = mediana + 3.5 × MAD
- Umbrales por hora del día para manejar estacionalidad
- Persiste el baseline en `data/baseline_cache.json` para sobrevivir reinicios
- Reglas específicas: credential theft (≥10 intentos 401/403 por IP), ERROR spike, LLM abuse, LLM cost anomaly

#### Capa 2: Z-score Robusto Histórico

Detecta cambios graduales que no superan el umbral absoluto pero son anómalos frente al historial reciente.

- Compara la ventana actual contra las últimas 10 ventanas limpias
- Usa **robust z-score** basado en MAD en lugar de z-score clásico
- Tipos monitoreados: LLM_ERROR, LLM_TIMEOUT, SECURITY, ERROR, WARNING, LLM_REQUEST
- Umbral: robust_z > 2.5 → MEDIUM, > 3.5 → HIGH
- Excluye ventanas con alertas previas del baseline para prevenir **concept drift**

#### Capa 3: Detección por Aplicación

Detecta ataques focalizados en una sola aplicación SAP que el total global no detectaría.

- Aplica z-score robusto individualmente a cada una de las 10 aplicaciones SAP
- Compara errores (ERROR, LLM_ERROR, LLM_TIMEOUT, SECURITY) por app vs su propio historial
- Umbral: robust_z > 3.0 → MEDIUM, > 3.5 → HIGH

#### Capa 4: Isolation Forest (ML No Supervisado)

Detecta combinaciones inusuales de múltiples variables simultáneamente.

- Features: `log_type_enc`, `http_status_code`, `llm_response_time_ms`, `client_ip_enc`, `is_llm`, `llm_provider_enc`
- `contamination=0.05`: estima que ~5% de los registros son anómalos
- Entrenado sobre historial limpio cuando hay ≥500 registros históricos disponibles
- **Sistema de corroboración (voting):** el IF solo envía alerta si al menos una de las capas 1-3 también disparó. Esto elimina falsos positivos constantes del IF en ventanas normales.

---

### 2.3 `hana.py` — Persistencia en SAP HANA Cloud

Gestiona la conexión y escritura en SAP HANA Cloud (BTP Trial, plan Free Tier).

**Tablas:**
- `SAP_LOGS`: cada registro de cada ventana analizada (window_id, log_type, application, http_status_code, client_ip, llm_cost_usd, llm_response_time_ms, llm_provider, region)
- `SAP_ALERTS`: cada alerta enviada al endpoint SAP (timestamp, alert_type, severity, message, status_code, window_start, response_ms)

**Configuración:** SSL/TLS en puerto 443, `sslValidateCertificate=False` para entorno de desarrollo.

---

### 2.4 `dashboard.py` — Visualización en Streamlit

Dashboard interactivo para análisis en tiempo real de los datos capturados.

**Funcionalidades:**
- Fuente de datos configurable: HANA Cloud o CSV local
- Métricas globales: total de registros, distribución de tipos, tasa de error
- Tendencias entre ventanas: evolución temporal de cada tipo de log
- Análisis por aplicación SAP
- Log explorer: inspección por ventana individual
- Tabla de alertas enviadas con severidad y MTTD

---

## 3. Flujo de Datos

```
SAP API (/info, /logs/current)
        │
        ▼
   pipeline.py
   (polling 60s)
        │
        ├──► data/logs_YYYYMMDD_HHMM.csv
        │
        ▼
   detector.py
   ┌─────────────────────────────┐
   │  Capa 1: Reglas MAD         │
   │  Capa 2: Z-score robusto    │
   │  Capa 3: Por aplicación     │
   │  Capa 4: Isolation Forest   │
   └─────────────────────────────┘
        │
        ├──► SAP API POST /alert
        ├──► data/alerts_log.csv
        └──► hana.py → SAP_ALERTS (SAP HANA Cloud)

   dashboard.py (Streamlit)
        ├──► Lee SAP HANA Cloud
        └──► Lee CSV local
```

---

## 4. Decisiones Técnicas Clave

| Decisión | Alternativa descartada | Razón |
|----------|----------------------|-------|
| Detección no supervisada (IF, MAD) | Modelos supervisados (XGBoost, SVM) | No hay datos etiquetados en ciberseguridad real |
| MAD en vez de desviación estándar | std clásico | MAD es resistente a outliers — que son exactamente lo que queremos detectar |
| Exclusión de ventanas con alertas del baseline | Incluir todas las ventanas | Previene concept drift: el modelo no aprende los ataques como comportamiento normal |
| Sistema de corroboración para IF | IF independiente | IF marca siempre el X% más inusual; sin corroboración genera FP constantes en días normales |
| Umbrales horarios | Umbral único global | El sistema SAP tiene variabilidad natural por hora del día |
| Python + scikit-learn | SAP Analytics Cloud nativo | Tiempo de desarrollo 10x menor; los datos persisten en HANA de todas formas |
| Polling cada 60s | Webhook o cron | Detecta nuevas ventanas inmediatamente sin depender de infraestructura externa |

---

## 5. Métricas de Rendimiento

| Métrica | Valor |
|---------|-------|
| Ventanas analizadas | 250+ |
| Registros procesados | 1,000,000+ |
| MTTD promedio | < 3 segundos |
| MTTD mínimo | 476 ms |
| Alertas enviadas (ataques reales) | ~100 |
| Uptime del pipeline | 99%+ (8+ días continuos) |

---

## 6. Stack Tecnológico

| Componente | Tecnología |
|-----------|-----------|
| Lenguaje | Python 3.9 |
| ML / Detección | scikit-learn (IsolationForest, LabelEncoder) |
| Procesamiento | pandas, numpy |
| API Client | requests |
| Base de datos | SAP HANA Cloud (hdbcli) |
| Dashboard | Streamlit |
| Infraestructura SAP | SAP BTP Trial, Cloud Foundry |

---

*NOVA — Sistema de Detección de Amenazas en Tiempo Real para SAP*
*Hack IDM x SAP, Mayo 2026*
