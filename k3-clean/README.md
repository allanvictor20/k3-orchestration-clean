# K3 Orchestration

Multi-model AI orchestration platform for African institutions.  
Python FastAPI backend + React frontend. No Go, no Wails, no desktop bindings.

---

## Architecture

```
k3-orchestration/
├── orchestration-backend/      # Python FastAPI — the core engine
│   ├── main.py                 # FastAPI app, all HTTP endpoints
│   ├── classifier.py           # Decomposes prompts into typed subtasks
│   ├── router.py               # Routes subtasks to best provider
│   ├── executor.py             # Parallel execution with SSE events
│   ├── merger.py               # Claude synthesises all results
│   ├── retry.py                # Retry engine with provider fallback
│   ├── streaming.py            # SSE event bus
│   ├── sessions.py             # Persistent session memory
│   ├── memory.py               # Provider performance tracking
│   ├── audit.py                # Full audit trail per workflow
│   ├── hooks.py                # Pre/post orchestration hooks
│   ├── mcp_client.py           # MCP tool connections
│   ├── language_middleware.py  # African language support (Sunbird)
│   ├── normalizer.py           # Provider response normalisation
│   ├── validator.py            # Response confidence scoring
│   ├── workflow_state.py       # Canonical workflow state object
│   ├── models.py               # Pydantic models
│   ├── providers/              # Anthropic, OpenAI, Gemini, Perplexity, Sunbird
│   ├── mcp.json                # MCP server config
│   └── .env.example            # Required API keys
│
└── frontend/                   # React + Vite + Tailwind
    └── src/
        ├── main.tsx             # Entry point
        ├── App.tsx              # Root component
        ├── index.css            # Global styles
        ├── lib/
        │   ├── api.ts           # HTTP client for all backend endpoints
        │   ├── sse.ts           # SSE subscription manager
        │   └── utils.ts         # cn() helper
        └── components/orchestration/
            ├── OrchestrationPanel.tsx  # Main chat interface
            ├── WorkflowProgress.tsx    # Live SSE subtask display
            ├── SessionHistory.tsx      # Session sidebar
            └── LanguageSelector.tsx    # Language dropdowns
```

---

## Setup

### 1. Backend

```bash
cd orchestration-backend
cp .env.example .env
# Fill in your API keys in .env

pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8716 --reload
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

---

## API Keys (.env)

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
PERPLEXITY_API_KEY=pplx-...
SUNBIRD_API_KEY=...         # African language translation (optional)
```

---

## Providers & Task Routing

| Task type   | Default provider | Fallbacks              |
|-------------|-----------------|------------------------|
| coding      | Claude          | GPT-4o, Gemini         |
| reasoning   | GPT-4o          | Claude, Gemini         |
| research    | Perplexity      | Claude, GPT-4o         |
| translation | Sunbird         | Claude                 |
| writing     | Claude          | GPT-4o                 |

The router learns from performance history and promotes faster providers automatically.

---

## MCP Tools

Edit `orchestration-backend/mcp.json` to connect MCP tool servers:

```json
{
  "mcps": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home"]
    }
  }
}
```

---

## Hooks

Drop a `hook.py` into `orchestration-backend/hooks/<hook-name>/` to run custom
logic before or after every orchestration. See the auto-generated examples in
`hooks/enrich-context/` and `hooks/save-result/`.

---

## Language Support

Supports English, Luganda, Swahili, Acholi, Runyankole, and Kinyarwanda.  
Translation is handled by Sunbird AI. Set `SUNBIRD_API_KEY` in `.env`.
