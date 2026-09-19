# CloudServe Architecture & Governance

## System Architecture

```
[Customer Ticket Payload]
       │
       ▼
[Ingestion Module] (src/ingestion.py)
       │
       ▼
[Guardrails Engine] (src/guardrails.py) ──► [Unsafe / Injection] ──► [Escalate to Human]
       │ [Safe]
       ▼
[Category Classifier] (src/classifier.py)
       │
       ▼
[Knowledge Retrieval (RAG)] (src/retrieval.py)
       │
       ▼
[Decision Router Engine] (src/router.py)
       ├── [Confidence < 0.60] ──► [Escalate to Tier-2 Human Support]
       └── [Confidence >= 0.60] ──► [Response Generator LLM] (src/generator.py)
                                           │
                                           ▼
                              [SQLite Decision Database] (src/db.py)
```

## Modular Structure
- `src/ingestion.py`: Normalizes and cleans customer input payload.
- `src/guardrails.py`: Detects PII and prompt injection attacks.
- `src/classifier.py`: Predicts intent categories and confidence scores.
- `src/retrieval.py`: TF-IDF similarity search over Knowledge Base (`storage/kb.json`).
- `src/router.py`: Composite score evaluation against threshold $T=0.60$.
- `src/generator.py`: Generates context-grounded response via OpenRouter.
- `src/db.py`: Logs query details, scores, and decisions to SQLite database (`storage/governance.db`).
