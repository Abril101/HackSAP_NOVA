# NOVA — SAP Security Operations Center
## Presentación: Hack IDM x SAP — Live Defense Challenge

---

## SLIDE 1 — Portada

**NOVA**
Sistema de Detección de Amenazas en Tiempo Real para SAP
Hack IDM x SAP · Live Security Operations Center Defense

Equipo: [nombre del equipo]

---

## SLIDE 2 — El problema

SAP opera sistemas empresariales críticos: finanzas, compras, RRHH, nube.
Un ataque no detectado a tiempo puede costar millones.

**El reto:** detectar amenazas en logs SAP en menos de 30 minutos, de forma automática.

Tres tipos de amenaza que debíamos detectar:
- **Robo de credenciales** — ataques de fuerza bruta
- **Spikes de seguridad** — picos anómalos de errores
- **Abuso de LLM** — uso malicioso de capacidades de IA integradas en SAP

---

## SLIDE 3 — Nuestra solución: NOVA

**NOVA** es un pipeline automático de detección multicapa que:
1. Ingesta logs de la API SAP cada 30 minutos
2. Analiza con 4 capas de detección complementarias
3. Envía alertas al endpoint SAP en formato WHAT/WHEN/WHY
4. Visualiza todo en un dashboard en tiempo real

Tiempo de detección real demostrado: **entre 20 y 27 minutos** desde inicio de ventana (dentro del límite de 30 min requerido).

---

## SLIDE 4 — Arquitectura del sistema

```
API SAP  →  pipeline.py  →  detector.py  →  /alert endpoint SAP
                  ↓               ↓
            data/logs_*.csv   alerts_log.csv
                  ↓
            dashboard.py (Streamlit)
```

**pipeline.py** — Ingesta inteligente:
- Modo descubrimiento: aprende en qué minuto del ciclo aparecen los datos
- Modo optimizado: dispara exactamente cuando llegan los datos + segundo disparo a +30s
- Nunca analiza la misma ventana dos veces

**detector.py** — Detección multicapa:
- 4 capas independientes que se complementan

**dashboard.py** — Visualización:
- Auto-refresh configurable (30/60/120s)
- Tendencias históricas, alertas con tiempo de respuesta, análisis LLM

---

## SLIDE 5 — Las 4 capas de detección

### Capa 1: Reglas con umbrales dinámicos (3-sigma)
Cada umbral se calibra automáticamente con el historial de los últimos 10 ciclos.
- ERROR > media + 3σ → alerta HIGH
- SECURITY > media + 3σ → alerta HIGH
- LLM_ERROR + LLM_TIMEOUT > umbral combinado → alerta MEDIUM

**Por qué 3-sigma:** probabilidad de falso positivo ≈ 0.3% por tipo por ventana.

### Capa 2: Z-score histórico (series de tiempo)
Compara la ventana actual contra el promedio de las últimas 10 ventanas.
- Z > 2 → MEDIUM
- Z > 3 → HIGH

Detecta cambios graduales que las reglas fijas no verían.

### Capa 3: Detección por aplicación
Mismo fundamento estadístico aplicado individualmente a cada app SAP:
sap-analytics-cloud, sap-ariba, sap-btp-cf, sap-concur, sap-s4hana, etc.

Detecta el caso donde **una sola app falla silenciosamente** mientras el total global parece normal.

### Capa 4: Isolation Forest (ML no supervisado)
Entrenado sobre el historial acumulado de ventanas anteriores.
Detecta combinaciones inusuales de variables que las reglas no capturan.

Features usadas: tipo de log, HTTP status code, tiempo de respuesta LLM, IP del cliente, si es LLM, proveedor LLM.

**Diseño clave:** el IF solo dispara alerta si al menos otra capa (reglas o z-score) también detectó algo en esa ventana. Esto evita falsos positivos — con `contamination=0.05` el modelo siempre marcará el 5% más inusual como anomalía, incluso en ventanas normales. La corroboración entre capas es lo que hace la alerta confiable.

---

## SLIDE 6 — Datos reales capturados

Durante el evento capturamos más de **42 ventanas** — más de **211,000 registros**.

Distribución normal del sistema SAP:
- ~21% errores en todas las apps y regiones (distribución uniforme)
- LLM_REQUEST: ~537 eventos por ventana (baseline)
- LLM_ERROR: ~150 eventos por ventana (baseline)
- WARNING: ~566 eventos por ventana (baseline)

Correlaciones descubiertas con is_error:
- http_status_code: 0.668 (feature más importante)
- llm_response_time_ms: 0.211 (feature secundario)
- llm_cost_usd: 0.004 (descartado — sin valor predictivo)

---

## SLIDE 7 — Alertas enviadas (Go Live — 4 de mayo)

En el primer ciclo con datos reales detectamos un **evento de anomalía masiva**:

| Alerta | Severidad | Detalle |
|--------|-----------|---------|
| ERROR spike 3-sigma | HIGH | 520 errores vs umbral de 514 |
| LLM_ERROR histórico | HIGH | 445 eventos vs avg=150 (z=21.5) |
| LLM_TIMEOUT histórico | HIGH | 266 eventos vs avg=82 (z=12.0) |
| LLM_REQUEST histórico | HIGH | 1,533 requests vs avg=537 (z=57.3) |
| Error spikes por app | HIGH | 9 apps con spikes simultáneos |
| Isolation Forest | MEDIUM | 823 registros anómalos detectados |

**Tiempo de respuesta:** entre 20 y 27 minutos desde el inicio de la ventana — confirmado en múltiples ciclos, siempre dentro del límite de 30 min.

---

## SLIDE 8 — Observación importante (honestidad técnica)

Durante el análisis detectamos un **artefacto de reinicio**: cuando el pipeline se reiniciaba con pocas ventanas disponibles, el baseline calculado era incorrecto y generaba z-scores inflados.

**Solución implementada:** baseline cache persistente en JSON.
- Si hay ≥5 ventanas → calcula y guarda el baseline
- Si hay <5 ventanas → carga el baseline guardado del último ciclo

Esta es la diferencia entre un sistema de producción y un prototipo: detectar y corregir los casos edge.

---

## SLIDE 9 — Dashboard en tiempo real

El dashboard Streamlit muestra:

- **Estado en vivo**: conexión al servidor, registros en ventana actual, ventanas capturadas
- **Tendencias entre ventanas**: gráfica de LLM_ERROR, LLM_TIMEOUT, SECURITY, ERROR, WARNING a lo largo del tiempo
- **Historial de alertas**: total HIGH/MEDIUM, tiempo de respuesta promedio/min/max con gráfica
- **Análisis LLM**: tasa de error, costo promedio/máximo, top 5 requests más costosos
- **Explorador de logs**: filtrado por tipo y aplicación SAP

---

## SLIDE 10 — Evaluación del modelo

Sin datos etiquetados (aprendizaje no supervisado), no podemos calcular accuracy clásico.
Lo que sí podemos demostrar:

| Capa | Fundamento | Falso positivo estimado |
|------|-----------|------------------------|
| Reglas 3-sigma | Estadístico | ~0.3% por tipo por ventana |
| Z-score histórico | Estadístico | ~0.1% (z>3) |
| Por aplicación | Estadístico | ~0.1% (z>3) |
| Isolation Forest | ML | No cuantificable sin labels |

**Observación empírica:** 3+ días de operación sin falsos positivos constantes.
Las alertas enviadas corresponden a eventos estadísticamente significativos.

---

## SLIDE 11 — Lo que aprendimos

1. **Los datos reales son siempre más complejos que los simulados.** Descubrimos que todas las apps y regiones tienen tasas de error casi idénticas (~21%), lo que hace más difícil la detección granular.

2. **Los umbrales fijos fallan; los dinámicos escalan.** El sistema recalibra automáticamente cada vez que tiene suficiente historial.

3. **La detección multicapa es más robusta que cualquier capa sola.** Hay alertas que solo detecta el z-score, otras que solo detecta el IF, otras que ambas confirman.

4. **La observabilidad importa tanto como la detección.** El dashboard fue crítico para entender el comportamiento del sistema en tiempo real.

---

## SLIDE 12 — Trabajo futuro

- **Validación con red team**: simular los 3 tipos de amenaza y medir recall real
- **HANA Cloud**: conectar el sistema a SAP HANA para consultas SQL directas sobre los logs
- **Optimizar contamination de IF**: con datos etiquetados, buscar el valor óptimo en vez de asumir 5%
- **Ampliar ventana histórica**: más de 10 ciclos para umbrales más robustos
- **Alertas correlacionadas**: si 3+ apps fallan simultáneamente, escalar severidad automáticamente

---

## SLIDE 13 — Cierre

**NOVA detecta, en tiempo real, lo que un humano tardaría horas en encontrar.**

- Pipeline inteligente que aprende el timing del sistema
- 4 capas de detección complementarias
- Dashboard en vivo para el equipo SOC
- Alertas enviadas en formato estándar en <30 minutos

> "Un sistema de seguridad no se evalúa solo por lo que detecta, sino también por lo que no dispara en falso."

---

*Sistema NOVA — desarrollado durante Hack IDM x SAP, mayo 2026*
