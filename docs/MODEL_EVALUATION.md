# Evaluación del Modelo — NOVA
## Hack IDM x SAP — Live Security Operations Center Defense

---

## El problema fundamental de la evaluación

El sistema NOVA usa **aprendizaje no supervisado** para detectar anomalías en logs de SAP. A diferencia de modelos supervisados (clasificación, regresión), no contamos con datos etiquetados — nadie marcó qué logs son ataques reales y cuáles son comportamiento normal.

Esto significa que **no podemos calcular métricas clásicas** como accuracy, precision, recall o F1-score de forma honesta, porque no existe un ground truth contra el cual comparar.

---

## Evaluación por capa

### Capa 1 — Reglas simples (umbrales dinámicos 3-sigma)

| Métrica | Valor |
|---|---|
| Base estadística | Media + 3 desviaciones estándar sobre historial deslizante de 10 ventanas |
| Probabilidad de falso positivo | ~0.3% por tipo de log por ventana (asumiendo distribución normal) |
| Datos de calibración | 41+ ventanas reales (~205,800 registros) |
| Observación empírica | No ha disparado alertas falsas constantes en 3+ días de operación |

Es la capa más confiable y la más interpretable. Cada alerta tiene una justificación cuantitativa directa.

### Capa 2 — Z-score histórico (series de tiempo)

| Umbral | Probabilidad de falso positivo |
|---|---|
| Z > 2 (MEDIUM) | ~2.3% |
| Z > 3 (HIGH) | ~0.1% |

Compara la ventana actual contra el promedio de las últimas 10 ventanas. Detecta cambios graduales que las reglas fijas no verían.

### Capa 3 — Detección por aplicación

- Mismo fundamento estadístico que z-score pero aplicado a cada app SAP individualmente
- Umbral z > 3.0 → ~0.1% de falso positivo por app por ventana
- Detecta casos donde una app falla silenciosamente mientras el total global parece normal

### Capa 4 — Isolation Forest

| Parámetro | Valor |
|---|---|
| Contamination | 0.05 (5%) |
| Entrenamiento | Historial acumulado de ventanas anteriores |
| Features | log_type_enc, http_status_code, llm_response_time_ms, client_ip_enc, is_llm, llm_provider_enc |

**Limitación importante:** con `contamination=0.05`, el modelo siempre marcará el 5% más inusual de los registros como anomalías — incluso si todo es normal. No es posible medir su accuracy sin datos etiquetados. Es la capa menos interpretable pero complementa las reglas detectando combinaciones inusuales de variables.

---

## Observaciones empíricas (3+ días de operación)

- El sistema opera desde el 30 de abril de 2026 sin disparar falsos positivos constantes
- Las caídas bruscas observadas en la gráfica de tendencias no generaron alertas incorrectas
- Ninguna IP ha superado el umbral de `credential_theft` (≥10 por ventana) — o no hay ataques de fuerza bruta o el umbral es conservador
- Las alertas enviadas corresponden a patrones estadísticamente anómalos, no a ruido aleatorio

---

## Correlaciones de features (41 ventanas, 205,800 registros)

| Feature | Correlación con is_error |
|---|---|
| http_status_code | 0.668 — feature más importante |
| llm_response_time_ms | 0.211 — feature secundario útil |
| llm_cost_usd | 0.004 — descartado del modelo |

---

## Limitaciones y trabajo futuro

1. **Sin validación contra ataques reales** — para medir recall se necesita un red team que simule los 3 tipos de amenazas (credential theft, security spike, LLM abuse) y verificar que el sistema los detecte.

2. **Isolation Forest no supervisado** — el parámetro `contamination=0.05` es una suposición, no un valor aprendido. Con datos etiquetados se podría optimizar.

3. **Distribución uniforme** — el análisis mostró que todas las apps, regiones y HTTP methods tienen tasas de error similares (~21%). Esto hace más difícil detectar anomalías sutiles a nivel granular.

4. **Ventana deslizante limitada** — el z-score usa solo las últimas 10 ventanas. Con más historial (semanas/meses) los umbrales serían más robustos.

---

## Conclusión para la presentación

> El modelo es **estadísticamente sólido pero no validado contra ataques reales**. La fortaleza del sistema está en su arquitectura multicapa — combina reglas interpretables calibradas con datos reales, análisis de series de tiempo y ML no supervisado. En un entorno de producción real, se requeriría un ejercicio de red team para medir sensibilidad (recall) ante amenazas confirmadas.

---

*Análisis basado en 41+ ventanas capturadas entre el 30 de abril y el 3 de mayo de 2026.*
