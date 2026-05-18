# Sistema NOVA — Documentación Técnica
## Hack IDM x SAP — Live Security Operations Center Defense

**Equipo:** NOVA  
**Fecha:** 1 de mayo de 2026  
**Autor:** Abril Álvarez Mercado

---

## ¿Qué hace el sistema?

NOVA es un sistema de detección de amenazas en tiempo real para logs de SAP. Cada 30 minutos, la API del hackathon publica un lote nuevo de logs de producción. El sistema:

1. **Descarga** los logs automáticamente
2. **Analiza** si hay comportamiento anómalo usando 4 capas de detección
3. **Manda una alerta** al endpoint SAP en menos de 30 minutos si detecta algo

Si no se manda alerta a tiempo → el sistema se bloquea por un día entero.

---

## Arquitectura

```
API SAP (logs cada 30 min)
        │
        ▼
  pipeline.py          ← descarga logs, guarda CSV, llama al detector
        │
        ▼
  detector.py          ← analiza y manda alertas automáticamente
        │
        ├── Capa 1: Reglas simples
        ├── Capa 2: Z-score histórico
        ├── Capa 3: Detección por aplicación
        └── Capa 4: Isolation Forest
        │
        ▼
  Endpoint SAP /alert  ← alerta recibida y registrada
        │
        ▼
  dashboard.py         ← visualización en http://localhost:8501
```

---

## Estructura de archivos

```
HackSAP/
├── pipeline.py         → ingesta de logs + llamada al detector
├── detector.py         → detección de anomalías + envío de alertas
├── dashboard.py        → interfaz Streamlit
├── eda.py              → script de análisis exploratorio
├── .env                → API keys (NO compartir)
├── data/               → CSVs con logs capturados por ventana
├── eda_output/         → gráficas generadas por el EDA
├── EDA_Report.md       → análisis exploratorio formal
└── TECHNICAL_DOC.md    → este documento
```

---

## Cómo correr el sistema

Necesitas 3 terminales abiertas:

**Terminal 1 — Pipeline (obligatorio, siempre activo):**
```bash
cd /Users/abrilalvarezmercado/Documents/HackSAP
python3 pipeline.py
```

**Terminal 2 — Dashboard (opcional, para visualizar):**
```bash
cd /Users/abrilalvarezmercado/Documents/HackSAP
python3 -m streamlit run dashboard.py
# Abre http://localhost:8501 en el navegador
```

**Terminal 3 — Detector manual (solo para pruebas):**
```bash
cd /Users/abrilalvarezmercado/Documents/HackSAP
python3 detector.py
# El detector ya corre automáticamente desde pipeline.py
# Solo usar esta terminal para debugging
```

> **Importante:** No cierres la laptop — el pipeline debe estar corriendo continuamente para no perder ventanas de datos.

---

## Variables de entorno (.env)

El archivo `.env` debe contener:
```
SAP_TOKEN=<tu_token>
SAP_BASE_URL=<url_base_de_la_api>
```

---

## Los datos — ¿qué son los logs?

La API devuelve logs de 10 tipos distintos, divididos en dos grupos:

**Logs de sistema:**
| Tipo | Descripción |
|---|---|
| INFO | Operaciones normales |
| WARNING | Algo inusual pero no crítico |
| ERROR | Fallo en el sistema |
| DEBUG | Mensajes de desarrollo |
| AUDIT | Registro de acciones de usuarios |
| PERF | Métricas de rendimiento |
| SECURITY | Eventos de seguridad |

**Logs LLM:**
| Tipo | Descripción |
|---|---|
| LLM_REQUEST | Llamada exitosa a un modelo de lenguaje |
| LLM_ERROR | Llamada a LLM que falló |
| LLM_TIMEOUT | Llamada a LLM que tardó demasiado |

**Baseline real (medido sobre 13+ ventanas):**

| Tipo | Promedio/ventana | Alerta si supera |
|---|---|---|
| LLM_REQUEST | 1,494 | 1,630 |
| INFO | 1,203 | 1,335 |
| WARNING | 583 | 650 |
| ERROR | 447 | 514 |
| LLM_ERROR | 422 | 495 |
| LLM_TIMEOUT | 207 | 251 |
| SECURITY | 84 | 105 |

---

## Las 4 capas de detección

### Capa 1 — Reglas simples
Detectan amenazas conocidas con umbrales fijos calibrados con datos reales.

| Regla | Cuándo dispara | Severidad |
|---|---|---|
| `credential_theft` | ≥10 errores HTTP 401/403 desde la misma IP en una ventana | HIGH |
| `security_spike` | Más de 514 errores ERROR o más de 105 eventos SECURITY | HIGH |
| `llm_abuse` | Más de 724 eventos LLM_ERROR + LLM_TIMEOUT combinados | MEDIUM |
| `llm_cost_anomaly` | Más de 213 requests con costo >$0.032 USD | MEDIUM |

**¿Por qué estos números?** Fueron calculados con el método 3-sigma (media + 3 desviaciones estándar) sobre 13 ventanas reales de datos. Representan lo que estadísticamente es "imposible en condiciones normales".

### Capa 2 — Z-score histórico
Compara los conteos de la ventana actual contra el promedio de las últimas 10 ventanas usando z-score (cuántas desviaciones estándar se aleja del promedio histórico).

- **Z > 2** → alerta MEDIUM
- **Z > 3** → alerta HIGH

Ventaja sobre las reglas fijas: **se adapta automáticamente** si el tráfico cambia con el tiempo.

### Capa 3 — Detección por aplicación
Hace el mismo análisis de z-score pero **por cada aplicación SAP por separado** (sap-ariba, sap-concur, sap-s4hana-sales, etc.).

Detecta casos donde una aplicación específica está fallando pero el total global parece normal — algo que las capas 1 y 2 no verían.

- **Z > 2.5** → alerta MEDIUM
- **Z > 3.5** → alerta HIGH

### Capa 4 — Isolation Forest
Modelo de Machine Learning no supervisado que detecta registros individuales "raros" basándose en sus características numéricas combinadas.

**Features usados:**
- Tipo de log (codificado)
- HTTP status code
- Costo LLM en USD
- Tiempo de respuesta LLM en ms
- IP del cliente (codificada)
- Si es log LLM o de sistema

**Cómo funciona:**
- Si hay ≥500 registros históricos: se entrena sobre el historial completo y evalúa la ventana actual
- Si no hay suficiente historial: se entrena y evalúa sobre la ventana actual
- Marca el 5% de registros más inusuales como anomalías
- Si entre esas anomalías hay ≥10 eventos sospechosos (SECURITY, ERROR, LLM_ERROR, LLM_TIMEOUT) → manda alerta

---

## Formato de las alertas

Todas las alertas siguen el formato **WHAT / WHEN / WHY** y tienen máximo 300 caracteres:

```
WHAT: <descripción del problema>
WHEN: <timestamp UTC ISO 8601>
WHY: <evidencia cuantitativa>
```

Ejemplo real enviado:
```
WHAT: Anomaly cluster detected by ML model. 
WHEN: 2026-05-01T00:42:20Z. 
WHY: 293 anomalous records — LLM_TIMEOUT:168, LLM_ERROR:17, ERROR:12, SECURITY:2.
```

---

## EDA — ¿qué encontramos?

El análisis exploratorio se hizo sobre 12 ventanas (63,909 registros). Hallazgos clave:

1. **La distribución es estable entre ventanas** — el sistema tiene un comportamiento muy predecible, lo que hace viable el enfoque estadístico.

2. **Los nulos son estructurales, no errores** — los logs de sistema no tienen campos LLM y viceversa. Ambos grupos coexisten en el mismo dataset.

3. **LLM_ERROR/TIMEOUT son normales en cantidad** — ~629 por ventana es el baseline. El detector original disparaba con ≥5, lo cual era un falso positivo garantizado cada ventana.

4. **El costo LLM tiene 10.7% de outliers por diseño** — ~178 requests costosos por ventana es normal para este sistema.

5. **Ninguna IP ha superado el umbral de credential_theft** — la amenaza de robo de credenciales no se ha materializado en los datos analizados.

Para el análisis completo ver `EDA_Report.md` y las gráficas en `eda_output/`.

---

## Dependencias

```bash
pip3 install requests pandas scikit-learn python-dotenv streamlit matplotlib seaborn
```

---

## Pendientes del equipo

| Tarea | Responsable | Estado |
|---|---|---|
| Crear instancia HANA Cloud | - | ⏳ Esperando soporte SAP (verificación SMS) |
| Conectar pipeline a HANA | - | ❌ Bloqueado por punto anterior |
| Deploy en SAP BTP | - | ❌ Bloqueado por HANA |
| AI Agent con HANA (bonus) | - | ❌ Bloqueado por HANA |
| Presentación final | - | ❌ Pendiente |

---

*Sistema corriendo desde el 30 de abril de 2026. Go Live: 4 mayo. Eliminatoria: 7 mayo.*
