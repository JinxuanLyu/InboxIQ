from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from agents.agent import run_pipeline

app = FastAPI(title="InboxIQ - Email Intelligence Agent")

HTML_FILE = Path(__file__).parent / "templates" / "index.html"


class EmailRequest(BaseModel):
    email_content: str
    email_date: str | None = None


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=HTML_FILE.read_text(encoding="utf-8"))


@app.post("/analyze")
async def analyze_email(payload: EmailRequest):
    email = payload.email_content.strip()
    if not email or len(email) < 20:
        return {"error": "Please paste a full email to analyze."}
    return await run_pipeline(email, payload.email_date)


@app.get("/health")
async def health():
    return {"status": "ok"}