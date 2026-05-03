import json
import re
import os
import uuid
import asyncio
from datetime import date
import vertexai
from google.adk.agents import LlmAgent
from google.adk.tools import agent_tool, FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from .triage import triage_agent
from .research import research_agent
from .drafter import drafter_agent

PROJECT_ID = "ieor-4576-jinxuan"
LOCATION = "us-central1"

os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = LOCATION
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"

vertexai.init(project=PROJECT_ID, location=LOCATION)

triage_tool = agent_tool.AgentTool(agent=triage_agent)
research_tool = agent_tool.AgentTool(agent=research_agent)
drafter_tool = agent_tool.AgentTool(agent=drafter_agent)

ROOT_INSTRUCTION = """You are an email intelligence orchestrator for busy startup founders.

Use your tools in this exact sequence to analyze an email:

STEP 0 — Call get_current_date first, before anything else.
  You need today's date to assess deadline urgency accurately.
  Pass this date to triage_agent in the next step.

STEP 1 — Call triage_agent with the full email text and today's date from step 0.
  It returns a JSON with classification (priority, category) and extracted sender info.

STEP 2 — Check the category from step 1.
  - If category is "newsletter" or "sales_outreach": SKIP research_agent.
  - Otherwise: call research_agent with the sender name, role, and company.

STEP 3 — Call drafter_agent with:
  - The original email
  - The full triage JSON from step 1
  - The research summary from step 2 (or "No research conducted" if skipped)

STEP 4 — Return a JSON object with exactly this structure:
{
  "classification": <classification object from step 1>,
  "extracted": <extracted object from step 1>,
  "research": <research text from step 2 or "No research conducted">,
  "replies": <replies array from step 3>
}"""

_session_service = InMemorySessionService()
_APP_NAME = "inboxiq"


def _make_date_tool(email_date: str | None):
    def get_current_date() -> dict:
        """Returns the reference date in YYYY-MM-DD format for deadline urgency assessment."""
        return {"date": email_date if email_date else str(date.today())}
    return FunctionTool(func=get_current_date)


def _build_root_agent(email_date: str | None) -> LlmAgent:
    return LlmAgent(
        name="root_agent",
        model="gemini-2.5-flash",
        instruction=ROOT_INSTRUCTION,
        tools=[_make_date_tool(email_date), triage_tool, research_tool, drafter_tool],
        description="Orchestrates email triage, sender research, and reply drafting.",
    )


def _clean_json(raw: str) -> str:
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _parse_final(final_text: str) -> dict:
    try:
        parsed = json.loads(_clean_json(final_text))
        return {
            "classification": parsed.get("classification", {}),
            "extracted": parsed.get("extracted", {}),
            "research": parsed.get("research", "No research conducted."),
            "replies": parsed.get("replies", []),
        }
    except Exception as e:
        print(f"[PARSE ERROR attempt 1] {e}")

    try:
        match = re.search(r'\{.*\}', final_text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            return {
                "classification": parsed.get("classification", {}),
                "extracted": parsed.get("extracted", {}),
                "research": parsed.get("research", "No research conducted."),
                "replies": parsed.get("replies", []),
            }
    except Exception as e:
        print(f"[PARSE ERROR attempt 2] {e}")

    return {
        "classification": {},
        "extracted": {},
        "research": "",
        "replies": [{"label": "Draft", "tone": "Neutral", "rationale": "Fallback.", "draft": final_text}],
    }


async def _run_pipeline(email_content: str, email_date: str | None) -> dict:
    session_id = str(uuid.uuid4())
    user_id = "founder"

    await _session_service.create_session(
        app_name=_APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    root_agent = _build_root_agent(email_date)

    runner = Runner(
        agent=root_agent,
        app_name=_APP_NAME,
        session_service=_session_service,
    )

    message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=f"Analyze this email:\n\n{email_content}")],
    )

    final_text = ""

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message,
    ):
        print(f"[EVENT] author={getattr(event, 'author', 'N/A')} | {str(event.content)[:100] if event.content else 'None'}")
        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    final_text += part.text

    print(f"[FINAL TEXT] {final_text[:500]}")
    return _parse_final(final_text)


async def run_pipeline(email_content: str, email_date: str | None = None) -> dict:
    try:
        return await asyncio.wait_for(_run_pipeline(email_content, email_date), timeout=90.0)
    except asyncio.TimeoutError:
        print("[TIMEOUT] Pipeline exceeded 90s")
        return {
            "classification": {},
            "extracted": {},
            "research": "",
            "replies": [{"label": "Timeout", "tone": "N/A", "rationale": "Pipeline timed out. Please try again.", "draft": ""}],
        }