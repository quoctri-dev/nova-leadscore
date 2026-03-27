# NoVa LeadScore — AI Lead Scoring Engine

Upload any CSV or Excel lead list → AI analyzes and scores each lead (0-100) → Download prioritized results.

## Quick Start

1. Clone & install:
   ```bash
   git clone https://github.com/quoctri-dev/nova-leadscore.git
   cd nova-leadscore
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Configure `.env`:
   ```bash
   cp .env.example .env
   # Add your API key (Gemini, Claude, or Groq)
   ```

3. Run:
   ```bash
   streamlit run app.py
   ```

## Features

- **AI-Powered Scoring**: Gemini analyzes leads → score + priority + reasoning
- **Smart Field Detection**: Auto-maps name, email, company, title from any CSV schema
- **Self-Healing Pipeline**: AI unavailable → automatic rule-based fallback
- **Provider-Agnostic**: Gemini/Claude/Groq — swap with 1 `.env` change
- **Visual Dashboard**: KPIs, priority distribution, score histogram
- **Batch Processing**: Up to 500 leads per upload

## Configuration

| Variable | Default | Options |
|----------|---------|---------|
| `LLM_MODEL` | `gemini/gemini-2.5-flash` | `claude-sonnet-4-6`, `groq/llama3-70b-8192` |
| `MAX_LEADS` | `500` | Any integer |
| `BATCH_SIZE` | `10` | 5-20 recommended |

See `.env.example` for all options.

## Architecture

```
config.py          → .env-driven configuration
providers.py       → LiteLLM router + retry + fallback
core/detector.py   → Field type detection + auto-mapping
core/scorer.py     → AI batch scoring + rule-based fallback
validate.py        → Pre-run 5-layer validation
app.py             → Streamlit UI (wiring layer)
```

## Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| "Missing API key" | Add `GOOGLE_AI_API_KEY` to `.env` |
| Scoring slow | Reduce `BATCH_SIZE` to 5 |
| AI errors | Check API key validity, or add `FALLBACK_LLM_MODEL` |

## License

MIT — Built by [Quoc Tri](https://novasentio.com)
