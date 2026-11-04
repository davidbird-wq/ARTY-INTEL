"""
Trainable AI Agent — FastAPI service ready for Render
Features:
  • Chat with tool/ability calling
  • Knowledge base (facts + Q&A)
  • Training endpoint & conversational training
  • Simple web UI
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Paths & persistence
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
KNOWLEDGE_FILE = DATA_DIR / "knowledge.json"

DATA_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = Field(default_factory=list)
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    used_tools: List[str] = Field(default_factory=list)
    session_id: str


class TrainRequest(BaseModel):
    """Train the agent with a new fact or Q&A pair."""
    fact: Optional[str] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class TrainResponse(BaseModel):
    success: bool
    message: str
    knowledge_count: int


# ---------------------------------------------------------------------------
# Knowledge Base
# ---------------------------------------------------------------------------
class KnowledgeBase:
    def __init__(self, path: Path):
        self.path = path
        self.data: Dict[str, Any] = {"facts": [], "qa_pairs": [], "version": 1}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {"facts": [], "qa_pairs": [], "version": 1}
        else:
            self.save()

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def add_fact(self, content: str, tags: Optional[List[str]] = None) -> str:
        fact_id = str(uuid.uuid4())[:8]
        entry = {
            "id": fact_id,
            "content": content.strip(),
            "tags": tags or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.data["facts"].append(entry)
        self.save()
        return fact_id

    def add_qa(self, question: str, answer: str) -> None:
        self.data["qa_pairs"].append({
            "question": question.strip().lower(),
            "answer": answer.strip(),
        })
        self.save()

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        query = query.lower()
        results = []

        # Search facts
        for fact in self.data.get("facts", []):
            score = 0
            content = fact["content"].lower()
            if query in content:
                score += 3
            for word in query.split():
                if word in content:
                    score += 1
            if score > 0:
                results.append({"type": "fact", "content": fact["content"], "score": score, "id": fact["id"]})

        # Search Q&A
        for qa in self.data.get("qa_pairs", []):
            score = 0
            q = qa["question"].lower()
            if query in q or q in query:
                score += 5
            for word in query.split():
                if word in q:
                    score += 1
            if score > 0:
                results.append({"type": "qa", "question": qa["question"], "answer": qa["answer"], "score": score})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def count(self) -> int:
        return len(self.data.get("facts", [])) + len(self.data.get("qa_pairs", []))


kb = KnowledgeBase(KNOWLEDGE_FILE)


# ---------------------------------------------------------------------------
# Tools / Abilities
# ---------------------------------------------------------------------------
class ToolResult:
    def __init__(self, name: str, output: str, success: bool = True):
        self.name = name
        self.output = output
        self.success = success


def tool_get_time(_: str = "") -> ToolResult:
    now = datetime.now().strftime("%A, %B %d %Y • %I:%M %p")
    return ToolResult("get_time", f"Current time is {now}")


def tool_calculate(expression: str) -> ToolResult:
    # Very safe calculator — only allow numbers and basic operators
    expression = expression.strip()
    if not re.match(r"^[\d\s\+\-\*\/\.\(\)%]+$", expression):
        return ToolResult("calculate", "I can only calculate simple arithmetic expressions.", success=False)
    try:
        # Replace % with /100 for percentage
        expr = expression.replace("%", "/100")
        result = eval(expr, {"__builtins__": {}}, {})
        return ToolResult("calculate", f"{expression} = {result}")
    except Exception as e:
        return ToolResult("calculate", f"Could not calculate: {e}", success=False)


def tool_remember(fact: str) -> ToolResult:
    if not fact or len(fact) < 3:
        return ToolResult("remember", "Please provide a fact to remember.", success=False)
    fact_id = kb.add_fact(fact)
    return ToolResult("remember", f"Got it! I've stored that as knowledge (id: {fact_id}).")


def tool_search_knowledge(query: str) -> ToolResult:
    results = kb.search(query)
    if not results:
        return ToolResult("search_knowledge", "I don't have any knowledge matching that yet.")
    lines = []
    for r in results:
        if r["type"] == "fact":
            lines.append(f"• {r['content']}")
        else:
            lines.append(f"• Q: {r['question']} → {r['answer']}")
    return ToolResult("search_knowledge", "Here's what I know:\n" + "\n".join(lines))


def tool_list_abilities(_: str = "") -> ToolResult:
    abilities = [
        "get_time          – tell the current date and time",
        "calculate         – evaluate simple math expressions",
        "remember          – store a new fact in my knowledge base",
        "search_knowledge  – look up what I've learned",
        "list_abilities    – show this list",
        "train (via API)   – add facts or Q&A pairs programmatically",
    ]
    return ToolResult("list_abilities", "My abilities:\n" + "\n".join(abilities))


TOOLS = {
    "get_time": tool_get_time,
    "calculate": tool_calculate,
    "remember": tool_remember,
    "search_knowledge": tool_search_knowledge,
    "list_abilities": tool_list_abilities,
}


# ---------------------------------------------------------------------------
# Simple Intent + Tool Router
# ---------------------------------------------------------------------------
def detect_and_run_tools(message: str) -> List[ToolResult]:
    """Very lightweight pattern-based tool calling."""
    msg = message.lower().strip()
    results: List[ToolResult] = []

    # Time
    if any(w in msg for w in ["what time", "current time", "what's the time", "date today", "what day"]):
        results.append(tool_get_time())

    # Calculate
    calc_match = re.search(r"(?:calculate|compute|what is|what's)\s+([\d\s\+\-\*\/\.\(\)%]+)", msg)
    if calc_match:
        results.append(tool_calculate(calc_match.group(1)))
    elif re.match(r"^[\d\s\+\-\*\/\.\(\)%]+$", msg.strip()):
        results.append(tool_calculate(msg.strip()))

    # Remember
    remember_match = re.search(r"(?:remember that|remember this|learn that|store this|note that)\s+(.+)", msg, re.I)
    if remember_match:
        results.append(tool_remember(remember_match.group(1)))

    # Search knowledge
    if any(w in msg for w in ["what do you know about", "search knowledge", "do you know", "tell me about"]):
        # Extract the topic after the trigger phrase
        topic = re.sub(r".*(?:what do you know about|search knowledge|do you know|tell me about)\s*", "", msg, flags=re.I).strip(" ?")
        if topic:
            results.append(tool_search_knowledge(topic))
        else:
            results.append(tool_search_knowledge(msg))

    # List abilities
    if any(w in msg for w in ["what can you do", "your abilities", "list tools", "list abilities", "help"]):
        results.append(tool_list_abilities())

    return results


def generate_reply(message: str, history: List[ChatMessage]) -> tuple[str, List[str]]:
    """Generate a reply, optionally using tools and knowledge."""
    used_tools: List[str] = []

    # 1. Run any tools that match
    tool_results = detect_and_run_tools(message)
    tool_outputs = []
    for tr in tool_results:
        used_tools.append(tr.name)
        tool_outputs.append(tr.output)

    if tool_outputs:
        # If tools produced output, use that as the primary reply
        reply = "\n\n".join(tool_outputs)
        return reply, used_tools

    # 2. Check knowledge base for a good match
    results = kb.search(message, limit=3)
    if results:
        best = results[0]
        if best["score"] >= 3:
            if best["type"] == "qa":
                return best["answer"], used_tools
            else:
                return f"From my knowledge: {best['content']}", used_tools

    # 3. Fallback conversational replies
    msg = message.lower()
    if any(g in msg for g in ["hi", "hello", "hey", "yo"]):
        return "Hey! I'm your trainable AI agent. You can chat with me, teach me new facts, or ask me to use my tools. Type 'help' to see what I can do.", used_tools
    if "who are you" in msg or "what are you" in msg:
        return "I'm a lightweight trainable AI agent. I have tools (abilities) and a knowledge base you can expand by training me. Deployed ready for Render!", used_tools
    if "thank" in msg:
        return "You're welcome! Keep teaching me new things.", used_tools

    # Default
    return (
        "I'm not sure about that yet. You can teach me by saying "
        "\"remember that ...\" or use the Train panel. "
        "You can also ask me the time, to calculate something, or type 'help'.",
        used_tools,
    )


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Trainable AI Agent",
    description="A simple AI chatbot with tools/abilities and training features. Ready for Render.",
    version="1.0.0",
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    reply, used_tools = generate_reply(req.message, req.history)
    return ChatResponse(reply=reply, used_tools=used_tools, session_id=session_id)


@app.post("/train", response_model=TrainResponse)
async def train(req: TrainRequest):
    if req.fact:
        kb.add_fact(req.fact, req.tags)
        return TrainResponse(
            success=True,
            message=f"Learned new fact: {req.fact[:80]}...",
            knowledge_count=kb.count(),
        )
    if req.question and req.answer:
        kb.add_qa(req.question, req.answer)
        return TrainResponse(
            success=True,
            message=f"Learned Q&A pair.",
            knowledge_count=kb.count(),
        )
    raise HTTPException(status_code=400, detail="Provide either 'fact' or both 'question' and 'answer'.")


@app.get("/knowledge")
async def get_knowledge():
    return {
        "facts": kb.data.get("facts", []),
        "qa_pairs": kb.data.get("qa_pairs", []),
        "count": kb.count(),
    }


@app.post("/import")
async def import_knowledge(request: Request):
    """Import training data from a previously exported JSON file."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    facts = body.get("facts", [])
    qa_pairs = body.get("qa_pairs", [])

    if not isinstance(facts, list) or not isinstance(qa_pairs, list):
        raise HTTPException(status_code=400, detail="Expected 'facts' and 'qa_pairs' arrays")

    imported_facts = 0
    imported_qa = 0

    for fact in facts:
        if isinstance(fact, dict) and fact.get("content"):
            kb.add_fact(fact["content"], fact.get("tags", []))
            imported_facts += 1
        elif isinstance(fact, str) and fact.strip():
            kb.add_fact(fact.strip())
            imported_facts += 1

    for qa in qa_pairs:
        if isinstance(qa, dict) and qa.get("question") and qa.get("answer"):
            kb.add_qa(qa["question"], qa["answer"])
            imported_qa += 1

    return {
        "success": True,
        "message": f"Imported {imported_facts} facts and {imported_qa} Q&A pairs",
        "knowledge_count": kb.count(),
        "imported_facts": imported_facts,
        "imported_qa": imported_qa,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "knowledge_items": kb.count()}


# For local development
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
