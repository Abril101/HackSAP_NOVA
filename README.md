# NOVA — Real-Time Threat Detection System for SAP

🥇 **1st place — SAP x SEIDM Hackathon 2026** (21 teams, 100+ participants, Tec de Monterrey)

NOVA is an unsupervised anomaly detection system that monitors SAP BTP logs in real time, detects coordinated cybersecurity attacks, and sends actionable alerts within seconds. Built over 6 weeks of continuous work (design → deployment) by a team of 5, it ran with over 99% uptime during 8 days of continuous operation.

---

## The problem

SAP systems generate a huge volume of logs distributed across multiple applications. A real attack rarely looks like a single suspicious event — it looks like a correlation of seemingly normal events happening across different applications at the same time. An isolated log entry can pass any single filter; the pattern only becomes visible once it's cross-referenced against other events in the same time window.

We had no labeled data for real attacks, so the challenge was designing unsupervised anomaly detection that was fast (alerting within seconds, not the 30-minute limit set by the challenge) and low on false positives, without losing sensitivity to distributed attacks.

## Approach: why 4 layers instead of a single model

Instead of betting everything on one ML model, we designed a layered detection pipeline, where each layer covers a type of signal the others can't catch on their own:

1. **MAD (Median Absolute Deviation) rules** — catches immediate volume spikes, robust to outliers (unlike classic standard deviation).
2. **Robust historical Z-score** — compares each 30-minute window against the system's recent behavior, catching gradual deviations that fixed rules would miss.
3. **Per-application SAP detection** — specifically targets *coordinated* attacks: when multiple SAP applications are affected simultaneously, the signal is far stronger than any single anomaly. This is how we caught attacks compromising up to 9 SAP applications at once.
4. **Isolation Forest + One-Class SVM (corroboration)** — captures anomalous patterns not detectable by log type, as a backstop for the statistical layers.

The most important finding of the project wasn't the most sophisticated model: it was that a **properly calibrated Z-score** caught threats that more complex models missed. Understanding the actual data distribution mattered more than algorithmic complexity.

---

## Architecture

```
SAP API (/info, /logs/current)
        │
        ▼
   pipeline.py  ──────────────────► data/logs_YYYYMMDD_HHMM.csv
   (60s polling)
        │
        ▼
   detector.py (4 layers)
   ├── Layer 1: MAD rules (dynamic thresholds)
   ├── Layer 2: Robust historical Z-score
   ├── Layer 3: Per-application SAP detection (coordinated attacks)
   └── Layer 4: Isolation Forest + One-Class SVM (corroboration)
        │
        ├──► POST /alert (SAP endpoint)
        ├──► data/alerts_log.csv
        └──► SAP HANA Cloud (via hana.py)

   dashboard.py (Streamlit) ──► real-time visualization + threat-response chatbot
```

---

## Results

- **Average MTTD (Mean Time To Detect): 2.6 seconds** — the challenge's limit was 30 minutes
- **89% of alerts** sent in under 5 seconds
- **3 real attacks** detected during the hackathon, including one coordinated attack across 9 SAP applications simultaneously
- **>99% uptime** running on SAP HANA Cloud and SAP BTP over 8 days of continuous operation
- Significant reduction in false positives compared to the single-model approaches we tried initially
- Every alert includes actionable context (what happened, when, and why), plus an integrated chatbot to speed up the security team's response

## Limitations and next steps

- Since the system is unsupervised, threshold calibration (MAD, Z-score) was tuned iteratively against the traffic observed during the hackathon; a production deployment would need validation against a longer, more varied traffic period.
- The system was evaluated on the SAP BTP Trial environment provided for the challenge, not on a production environment with the scale and log diversity of a real enterprise.

---

## Requirements

```
pip install pandas numpy scikit-learn requests python-dotenv streamlit hdbcli
```

## Configuration

Create a `.env` file in the project root with the following variables:

```
SAP_TOKEN=your_token_here
SAP_BASE_URL=your_server_url_here
HANA_HOST=your_hana_host
HANA_PORT=443
HANA_USER=your_username
HANA_PASSWORD=your_password
```
> **Never commit the `.env` file to the repository.**

## Running the system

### 1. Ingestion and detection pipeline (background)
```
nohup python3 -u pipeline.py > data/pipeline.log 2>&1 &
```
Check that it's running:
```
tail -f data/pipeline.log
```

### 2. Visualization dashboard
```
streamlit run dashboard.py
```
Opens at `http://localhost:8501`

### 3. Detection only (on the most recent CSV)
```
python3 detector.py
```

---

## Project files

| File | Description |
|---|---|
| `pipeline.py` | Log ingestion from the SAP API, 60s polling |
| `detector.py` | Detection engine with 4 layers of unsupervised ML |
| `hana.py` | Connection and writes to SAP HANA Cloud |
| `dashboard.py` | Interactive Streamlit dashboard |
| `eda.py` | Exploratory data analysis |
| `analysis.py` | Supplementary analysis scripts |

---

## Tech stack

- Python 3.9
- scikit-learn (IsolationForest, One-Class SVM)
- pandas, numpy
- SAP HANA Cloud (hdbcli)
- Streamlit
- SAP BTP Trial

## Team

Built together with Cedrick Treviño, Steffany Lara, Ana Lidia Hernández Díaz, and Brisma Teresita Alvarez Valdez, as part of the SAP x SEIDM Hackathon 2026 at Tec de Monterrey.
