# InboxIQ — Email Intelligence Agent

> Paste any email. Get instant triage, key context extraction, and three strategic reply drafts — built for founders who can't afford to think slowly.

**Live URL:** `https://inboxiq-192593734991.us-central1.run.app/`

---

## What it does

1. **Paste** a raw email and optionally set the date it was sent
2. **Classify** — priority, category, sentiment, action required, deadline with specific dates
3. **Research** — live web search on the sender for high-value emails (investor, customer, hiring, partnership)
4. **Draft** — 3 strategic reply options with different approaches and rationale

---

## Run locally

### Prerequisites
- Python 3.11+
- GCP project with Vertex AI API enabled (`ieor-4576-jinxuan`)
- Authenticated: `gcloud auth application-default login`

### Install & run

```bash
unzip email-agent-adk-final.zip && cd email-agent-adk-final
pip install -r requirements.txt
export GOOGLE_CLOUD_PROJECT=ieor-4576-jinxuan
export GOOGLE_CLOUD_LOCATION=us-central1
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
uvicorn main:app --reload --port 8080
```

Open `http://localhost:8080`

---

## Deploy to Cloud Run

```bash
gcloud run deploy inboxiq \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=ieor-4576-jinxuan,GOOGLE_CLOUD_LOCATION=us-central1,GOOGLE_GENAI_USE_VERTEXAI=TRUE
```

---

## Class concepts used

### 1. Context Engineering
**Files:** `agents/agent.py`, `agents/triage.py`, `agents/drafter.py`

Every agent in the pipeline has a carefully designed system prompt using positive constraints — telling the model exactly what to do rather than what not to do. The `ROOT_INSTRUCTION` in `agent.py` explicitly sequences STEP 0–4, ensuring the orchestrator always calls `get_current_date` first, routes conditionally based on triage output, and returns a specific JSON structure. Sub-agent instructions define exact output schemas, tone rules, and reasoning requirements.

```python
ROOT_INSTRUCTION = """...
STEP 0 — Call get_current_date first, before anything else.
STEP 1 — Call triage_agent with the full email text and today's date.
STEP 2 — Check the category. If newsletter or sales_outreach: SKIP research_agent.
STEP 3 — Call drafter_agent with email + triage JSON + research summary.
STEP 4 — Return a JSON object with exactly this structure: ..."""
```

### 2. Agent Framework — Google ADK `LlmAgent`
**File:** `agents/agent.py`

The pipeline is built with Google Agent Development Kit (ADK). A `root_agent` orchestrates three specialist sub-agents (`triage_agent`, `research_agent`, `drafter_agent`), each wrapped as an `AgentTool`. The root agent decides at runtime which tools to call and in what order — this is genuine agent orchestration, not a hardcoded pipeline.

```python
triage_tool = agent_tool.AgentTool(agent=triage_agent)
research_tool = agent_tool.AgentTool(agent=research_agent)
drafter_tool = agent_tool.AgentTool(agent=drafter_agent)

root_agent = LlmAgent(
    name="root_agent",
    model="gemini-2.5-flash",
    tools=[date_tool, triage_tool, research_tool, drafter_tool],
)
```

### 3. Tool Use — `get_current_date` FunctionTool + Google Search grounding
**Files:** `agents/agent.py`, `agents/research.py`

Two tools in play:

**`get_current_date`** — A `FunctionTool` registered on `root_agent`. Called as STEP 0 before every analysis. Accepts an optional user-supplied date (from the UI date picker) so historical emails can be analyzed with the correct temporal context. The model uses this date to convert relative deadlines ("end of this week") into specific dates.

```python
def _make_date_tool(email_date: str | None):
    def get_current_date() -> dict:
        """Returns the reference date for deadline urgency assessment."""
        return {"date": email_date if email_date else str(date.today())}
    return FunctionTool(func=get_current_date)
```

**Google Search grounding** — `research_agent` uses ADK's built-in `google_search` tool to search the web for background on the sender. Results are summarized and passed to `drafter_agent` to personalize the reply.

```python
from google.adk.tools import google_search

research_agent = LlmAgent(
    name="research_agent",
    tools=[google_search],
    ...
)
```

### 4. Multi-Agent Orchestration — Conditional routing
**File:** `agents/agent.py` — `ROOT_INSTRUCTION`

Three specialist agents run in sequence, but with conditional routing: `newsletter` and `sales_outreach` emails skip `research_agent` entirely. The root agent reads triage output and decides at runtime whether research is worth the cost. This saves one full LLM call per low-value email — directly impacting unit economics.

```
root_agent
  STEP 0 → get_current_date (always)
  STEP 1 → triage_agent (always)
  STEP 2 → research_agent (investor / customer / partnership / hiring only)
  STEP 3 → drafter_agent (always)
```

### 5. Structured Output — JSON schema enforcement
**Files:** `agents/triage.py`, `agents/drafter.py`

Both `triage_agent` and `drafter_agent` are instructed to return JSON objects conforming to a defined schema. The triage schema (priority, category, sentiment, deadline, sender info) is consumed by `drafter_agent` to generate context-aware replies. Structured output enables reliable agent chaining without brittle string parsing.

---

## Project structure

```
email-agent-adk-final/
├── main.py                  # FastAPI app
├── agents/
│   ├── agent.py             # root_agent + run_pipeline (orchestration core)
│   ├── triage.py            # triage_agent — classification + extraction
│   ├── research.py          # research_agent — Google Search grounding
│   ├── drafter.py           # drafter_agent — reply generation
│   ├── state.py             # EmailState TypedDict
│   └── __init__.py
├── templates/
│   └── index.html           # Frontend UI
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Token economics (back-of-envelope)

| Step | Tokens (est.) | Cost @ Gemini 2.5 Flash |
|------|--------------|--------------------------|
| get_current_date tool call | ~200 in / ~10 out | ~$0.00005 |
| Triage agent | ~900 in / ~500 out | ~$0.0004 |
| Research agent (when triggered) | ~800 in / ~400 out | ~$0.0003 |
| Drafter agent | ~1,500 in / ~900 out | ~$0.0006 |
| **Per email (full pipeline)** | ~3,800 total | **~$0.0013** |
| **Per email (newsletter, skip research)** | ~2,800 total | **~$0.0010** |

100 emails/day → ~$3–4/month per user in model costs. Priced at $29/month → ~85% gross margin.

---

## Tech stack

- **Agent framework:** Google ADK (`LlmAgent`, `AgentTool`, `FunctionTool`)
- **Models:** Gemini 2.5 Flash on Vertex AI
- **Backend:** FastAPI + Uvicorn
- **Deployment:** Google Cloud Run
- **Frontend:** Vanilla HTML/CSS/JS

## Notes: Codes are powered by Claude, but the author gave the thoughts.
