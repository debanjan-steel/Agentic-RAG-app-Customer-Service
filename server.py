import os
import glob
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from agentic_rag import process_agentic_chat, MOCK_ORDERS

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Amazon Customer Service Agentic RAG")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files directory
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

class ChatRequest(BaseModel):
    message: str

@app.get("/")
async def get_index():
    index_path = static_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path)

@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    try:
        result = process_agentic_chat(req.message.strip())
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/orders")
async def get_mock_orders():
    import agentic_rag
    print("MOCK_ORDERS keys in server:", list(agentic_rag.MOCK_ORDERS.keys()))
    return agentic_rag.MOCK_ORDERS

@app.get("/api/policies")
async def get_policies():
    policy_files = glob.glob("./data/*.md")
    policies = []
    for f in policy_files:
        p = Path(f)
        content = p.read_text(encoding="utf-8")
        title = p.stem.replace("_", " ").title()
        policies.append({
            "filename": p.name,
            "title": title,
            "preview": content[:200] + "..."
        })
    return policies

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
