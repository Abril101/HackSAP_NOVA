# NOVA — Sistema de Detección de Amenazas en Tiempo Real para SAP

🥇 **1er lugar — Hackathon SAP x SEIDM 2026** (21 equipos, +100 participantes, Tec de Monterrey)

NOVA es un sistema de detección de anomalías no supervisado que monitorea logs de SAP BTP en tiempo real, detecta ataques de ciberseguridad coordinados y envía alertas automáticas accionables en cuestión de segundos. Desarrollado en 6 semanas de trabajo continuo (diseño → despliegue) por un equipo de 5 personas, operó con más de 99% de disponibilidad durante 8 días continuos de evaluación.

---

## El problema

Los sistemas SAP generan un volumen enorme de logs distribuidos entre múltiples aplicaciones. Un ataque real rara vez se ve como un solo evento sospechoso — se ve como una correlación de eventos *aparentemente normales* ocurriendo en distintas aplicaciones al mismo tiempo. Un registro aislado puede pasar cualquier filtro; el patrón solo se vuelve evidente cuando se cruza contra otros eventos de la misma ventana de tiempo.

No teníamos datos etiquetados de ataques reales para entrenar un clasificador supervisado, así que el reto era diseñar detección de anomalías no supervisada que fuera rápida (alertar en segundos, no en los 30 minutos que marcaba el límite del reto) y con pocos falsos positivos, sin perder sensibilidad a ataques distribuidos.

## Enfoque: por qué 4 capas en vez de un solo modelo

En vez de apostar todo a un modelo de ML, diseñamos un pipeline de detección por capas, donde cada una cubre un tipo de señal que las otras no capturan:

1. **Reglas MAD (Median Absolute Deviation)** — detecta spikes inmediatos en volumen, robusta a outliers (a diferencia de desviación estándar clásica).
2. **Z-score robusto histórico** — compara cada ventana de 30 minutos contra el comportamiento reciente del sistema, detectando desviaciones graduales que las reglas fijas no verían.
3. **Detección por aplicación SAP** — busca específicamente ataques *coordinados*: cuando múltiples aplicaciones SAP se ven afectadas simultáneamente, la señal es mucho más fuerte que cualquier anomalía individual. Así detectamos ataques con hasta 9 aplicaciones comprometidas al mismo tiempo.
4. **Isolation Forest + One-Class SVM (corroboración)** — captura patrones anómalos no detectables por tipo de log, como respaldo de las capas estadísticas.

El hallazgo más importante del proyecto no fue el modelo más sofisticado: fue que un **Z-score correctamente calibrado** detectó amenazas que los modelos más complejos no lograban capturar. Entender la distribución real de los datos importó más que la complejidad del algoritmo.

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
   ├── Capa 3: Detección por aplicación SAP (ataques coordinados)
   └── Capa 4: Isolation Forest + One-Class SVM (corroboración)
        │
        ├──► POST /alert (endpoint SAP)
        ├──► data/alerts_log.csv
        └──► SAP HANA Cloud (via hana.py)

   dashboard.py (Streamlit) ──► visualización en tiempo real + chatbot de respuesta a amenazas
```

---

## Resultados

- **MTTD (Mean Time To Detect) promedio: 2.6 segundos** — el límite del reto era 30 minutos
- **89% de alertas** enviadas en menos de 5 segundos
- **3 ataques reales** detectados durante el hackathon, incluyendo uno coordinado en 9 aplicaciones SAP simultáneamente
- **>99% disponibilidad** del sistema sobre SAP HANA Cloud y SAP BTP durante 8 días de operación continua
- Reducción significativa de falsos positivos frente a los enfoques de un solo modelo que probamos inicialmente
- Cada alerta incluye contexto accionable (qué pasó, cuándo, por qué) más un chatbot integrado para agilizar la respuesta del equipo de seguridad

## Limitaciones y próximos pasos

- Al ser no supervisado, la calibración de umbrales (MAD, Z-score) se hizo de forma iterativa contra el comportamiento observado durante el hackathon; un despliegue productivo real necesitaría validación contra un periodo más largo y variado de tráfico.
- El sistema fue evaluado en el entorno de SAP BTP Trial provisto para el reto, no en un entorno productivo con la escala y diversidad de logs de una empresa real.

---

## Requisitos

```
pip install pandas numpy scikit-learn requests python-dotenv streamlit hdbcli
```

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

## Cómo correr el sistema

### 1. Pipeline de ingesta y detección (en background)
```
nohup python3 -u pipeline.py > data/pipeline.log 2>&1 &
```
Verificar que está corriendo:
```
tail -f data/pipeline.log
```

### 2. Dashboard de visualización
```
streamlit run dashboard.py
```
Se abre en `http://localhost:8501`

### 3. Solo detección (sobre el CSV más reciente)
```
python3 detector.py
```

---

## Archivos del proyecto

| Archivo | Descripción |
|---|---|
| `pipeline.py` | Ingesta de logs desde API SAP, polling cada 60s |
| `detector.py` | Motor de detección con 4 capas de ML no supervisado |
| `hana.py` | Conexión y escritura en SAP HANA Cloud |
| `dashboard.py` | Dashboard interactivo en Streamlit |
| `eda.py` | Análisis exploratorio de datos |
| `analysis.py` | Scripts de análisis complementario |

---

## Stack tecnológico

- Python 3.9
- scikit-learn (IsolationForest, One-Class SVM)
- pandas, numpy
- SAP HANA Cloud (hdbcli)
- Streamlit
- SAP BTP Trial

## Equipo

Proyecto desarrollado junto a Cedrick Treviño, Steffany Lara, Ana Lidia Hernández Díaz y Brisma Teresita Alvarez Valdez, como parte del Hackathon SAP x SEIDM 2026 en el Tec de Monterrey.
