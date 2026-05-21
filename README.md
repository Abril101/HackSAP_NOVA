# NOVA — Sistema de Detección de Amenazas en Tiempo Real para SAP
**Hack IDM x SAP 2026 | Live Security Operations Center Defense**

NOVA es un sistema de detección de anomalías no supervisado que monitorea logs de SAP en tiempo real, detecta ataques de ciberseguridad y envía alertas automáticas en menos de 3 segundos.

---

## Arquitectura

```
API SAP (/info, /logs/current)
        │
        ▼
   pipeline.py  ──────────────────► data/logs_YYYYMMDD_HHMM.csv
   (polling 60s)
        │
        ▼
   detector.py (4 capas)
   ├── Capa 1: Reglas MAD (umbrales dinámicos)
   ├── Capa 2: Z-score robusto histórico
   ├── Capa 3: Detección por aplicación SAP
   └── Capa 4: Isolation Forest (con corroboración)
        │
        ├──► POST /alert (endpoint SAP)
        ├──► data/alerts_log.csv
        └──► SAP HANA Cloud (via hana.py)

   dashboard.py (Streamlit) ──► visualización en tiempo real
```

---

## Requisitos

```bash
pip install pandas numpy scikit-learn requests python-dotenv streamlit hdbcli
```

---

## Configuración

Crea un archivo `.env` en la raíz del proyecto con las siguientes variables:

```
SAP_TOKEN=tu_token_aqui
SAP_BASE_URL=url_del_servidor_aqui
HANA_HOST=tu_host_hana
HANA_PORT=443
HANA_USER=tu_usuario
HANA_PASSWORD=tu_password
```

> **Nunca subas el archivo `.env` al repositorio.**

---

## Cómo correr el sistema

### 1. Pipeline de ingesta y detección (en background)

```bash
nohup python3 -u pipeline.py > data/pipeline.log 2>&1 &
```

Verificar que está corriendo:

```bash
tail -f data/pipeline.log
```

### 2. FastApi

```bash
uvicorn main:app --reload
```

Se abre en `http://localhost:8000`

### 3. Dashboard de visualización

```bash
streamlit run dashboard.py
```

Se abre en `http://localhost:8501`

### 4. Solo detección (sobre el CSV más reciente)

```bash
python3 detector.py
```

---

## Archivos del proyecto

| Archivo | Descripción |
|---------|-------------|
| `pipeline.py` | Ingesta de logs desde API SAP, polling cada 60s |
| `detector.py` | Motor de detección con 4 capas de ML no supervisado |
| `hana.py` | Conexión y escritura en SAP HANA Cloud |
| `dashboard.py` | Dashboard interactivo en Streamlit |
| `eda.py` | Análisis exploratorio de datos |
| `analysis.py` | Scripts de análisis complementario |

---

## Resultados

- **MTTD promedio: 2.6 segundos** (límite: 30 minutos)
- **89% de alertas** enviadas en menos de 5 segundos
- **3 ataques** detectados durante el hackathon

---

## Stack tecnológico

- Python 3.9
- scikit-learn (IsolationForest)
- pandas, numpy
- SAP HANA Cloud (hdbcli)
- Streamlit
- SAP BTP Trial
