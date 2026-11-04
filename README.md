# Trainable AI Agent

A lightweight **AI chatbot** with **tools/abilities** and **training features**, ready to deploy on [Render](https://render.com) as a free webservice.

## Features

### Abilities (Tools)
| Tool | Description | Example |
|------|-------------|---------|
| `get_time` | Current date & time | “What time is it?” |
| `calculate` | Simple arithmetic | “Calculate 15 * 7 + 3” |
| `remember` | Store a new fact | “Remember that my favorite color is blue” |
| `search_knowledge` | Search learned knowledge | “What do you know about blue?” |
| `list_abilities` | Show available tools | “Help” or “What can you do?” |

### Training
- **Conversational**: Say “remember that …”
- **UI Panel**: Add facts or Q&A pairs from the side panel
- **Export / Import**: Download or upload training data as JSON
- **API**: `POST /train` and `POST /import`
- Knowledge is stored in `data/knowledge.json`

### Endpoints
- `GET /` – Web chat UI
- `POST /chat` – Chat API
- `POST /train` – Add knowledge
- `POST /import` – Import training data (JSON)
- `GET /knowledge` – View knowledge base
- `GET /health` – Health check

## Quick Deploy on Render

1. Push this repo to GitHub.
2. Go to [Render Dashboard](https://dashboard.render.com) → **New** → **Web Service**.
3. Connect the repository.
4. Render will auto-detect `render.yaml`.  
   Or set manually:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Click **Create Web Service**.

That’s it — your AI will be live in a few minutes.

> **Note**: Free Render instances have an ephemeral filesystem. Knowledge added while the service is running will be lost on restart/redeploy. For permanent storage, later connect a free Postgres or use a volume.

## Local Development

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://localhost:8000

## Project Structure

```
ai-agent-render/
├── main.py              # FastAPI app + agent logic
├── requirements.txt
├── render.yaml          # Render blueprint
├── Procfile
├── data/
│   └── knowledge.json   # Persistent knowledge base
├── templates/
│   └── index.html       # Chat UI
└── static/
    ├── style.css
    └── app.js
```

## Extending

- Add new tools in the `TOOLS` dict and `detect_and_run_tools()` in `main.py`
- Swap the simple keyword matching for an LLM (OpenAI, Groq, etc.) later
- Connect a real database for permanent memory

---

Built to be simple, self-contained, and immediately deployable.
