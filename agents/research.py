"""
Research Agent
- Searches the web for background on the email sender using Google Search grounding
- Only called for high-value categories (investor, customer, partnership, hiring)
"""

from google.adk.agents import LlmAgent
from google.adk.tools import google_search

RESEARCH_INSTRUCTION = """You are a research assistant helping a startup founder prepare to reply to an email.

Search for background on the sender using the google_search tool and summarize in 3-5 sentences.
Focus on: what the company does, the sender's role, recent news, and why this matters for the reply.

If you cannot find useful information, say so briefly — do not make things up.
Return plain text, not JSON."""

research_agent = LlmAgent(
    name="research_agent",
    model="gemini-2.5-flash",
    instruction=RESEARCH_INSTRUCTION,
    tools=[google_search],
    description="Searches the web for background on the email sender to help personalize the reply.",
)