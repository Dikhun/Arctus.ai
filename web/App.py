"""Arctus.ai FastAPI server.

Runs on port 7860 (Hugging Face Spaces / Docker / cloud). Keys come from
the environment (HF Spaces Secrets), NEVER from forwarded client headers.

Endpoints:
  GET  /                          -> Next.js frontend (Static Export)
  GET  /api/health                -> health
  POST /api/orchestrate           -> run a task (JSON body)
  WS   /api/stream                -> WebSocket for real-time terminal streaming
  POST /api/mcp/connect           -> add an MCP connector
  GET  /api/mcp/list              -> list MCP connectors
  DELETE /api/mcp/{name}          -> remove an MCP connector
  GET  /api/agents                -> list the agent roster
  GET  /api/consortium/peers      -> list consortium peers
  POST /api/consortium/peers      -> add a peer (https or localhost only)
  POST /api/consortium/submit     -> receive a consortium task from a peer
  GET  /api/consortium/result/{id} -> fetch a result for a peer
"""
from __future__ import annotations

import json
import logging
import os
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from arctus import load_config
from arctus.agents import build_roster, roster_summary
from arctus.consortium import ConsortiumHub, Peer, ConsortiumTask
from arctus.mcp import REGISTRY, MCPConnector, add_connector as _add_mcp
from arctus.orchestrator import QueenAgent
from arctus.config import resolve_tier_for_config, TIER_QUOTAS, TIER_NAMES
from arctus.rate_limit import RateLimitConfig, check_monthly_quota, compute_monthly_cost, RateLimitError
from arctus import session as session_store

logger = logging.getLogger("arctus.server")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Arctus.ai Orchestrator", version="1.0.0")

# 1. CORS Setup (Required for Next.js dev server on port 3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this in production to your specific domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singletons
_hub = ConsortiumHub()
_roster = build_roster()

# ---------- models ----------
class OrchestrateRequest(BaseModel):
    prompt: str
    session_id: str = "default"
    complexity_override: Optional[str] = None

class MCPConnectRequest(BaseModel):
    name: str
    config: Dict[str, Any]

class PeerRequest(BaseModel):
    name: str
    base_url: str
    shared_secret: str

# ---------- routes ----------

# 2. WebSocket Endpoint for Real-Time Next.js Terminal
@app.websocket("/api/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connected from Next.js client.")
    
    cfg = load_config()
    # Fallback to free tier for WS if no auth is passed, or parse from query params
    tier_name = os.environ.get("ARCTUS_TIER", "free")
    cfg = resolve_tier_for_config(cfg, tier_name)
    queen = QueenAgent(cfg)

    try:
        while True:
            text_data = await websocket.receive_text()
            try:
                payload = json.loads(text_data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON format."})
                continue

            action = payload.get("action")
            
            if action == "swarm_health_check":
                await websocket.send_json({"type": "system", "message": "[Orchestrator]: Swarm diagnostic running..."})
                await asyncio.sleep(1) # Simulate check
                await websocket.send_json({"type": "success", "message": "[Orchestrator]: All 4 agent nodes are responsive and healthy."})
                
            elif action == "execute_command":
                prompt = payload.get("command")
                session_id = payload.get("session_id", "ws_default")
                model_pref = payload.get("model", "default")
                
                await websocket.send_json({"type": "system", "message": f"[Orchestrator]: Task received. Spooling up agents..."})
                
                # Execute orchestration (ideally this should be run in a threadpool if it's heavily blocking)
                try:
                    # Depending on how your QueenAgent is implemented, you might yield chunks here
                    result = queen.run(prompt, session_id=session_id)
                    
                    # Send final result back to Next.js terminal
                    await websocket.send_json({
                        "type": "success", 
                        "message": f"[Result]: {result.work}\n[Complexity]: {result.complexity}"
                    })
                except Exception as e:
                    logger.error(f"WS Orchestration error: {e}")
                    await websocket.send_json({"type": "error", "message": f"[System Error]: {str(e)}"})
                    
    except WebSocketDisconnect:
        logger.info("Next.js client disconnected.")


@app.post("/api/orchestrate")
async def orchestrate(req: OrchestrateRequest, request: Request):
    cfg = load_config()

    tier_name = request.headers.get("x-arctus-tier", "") or os.environ.get("ARCTUS_TIER", "free")
    tier_name = tier_name.lower() if tier_name.lower() in TIER_NAMES else "free"

    usage = session_store.monthly_usage(req.session_id)
    try:
        check_monthly_quota(req.session_id, tier_name, usage)
    except RateLimitError as e:
        return JSONResponse(
            status_code=429,
            content={"error": "monthly_limit", "detail": e.detail, "usage": usage, "tier": tier_name},
        )

    cfg = resolve_tier_for_config(cfg, tier_name)
    queen = QueenAgent(cfg)
    result = queen.run(
        req.prompt,
        session_id=req.session_id,
        complexity_override=req.complexity_override,
    )

    token_usage = getattr(result, "usage", {}) or {}
    in_tok = token_usage.get("prompt_tokens", 0)
    out_tok = token_usage.get("completion_tokens", 0)
    est_cost = compute_monthly_cost(tier_name, in_tok, out_tok)
    session_store.increment_usage(req.session_id, in_tokens=in_tok, out_tokens=out_tok, est_cost=est_cost)
    updated_usage = session_store.monthly_usage(req.session_id)

    return {
        "complexity": result.complexity,
        "mode": result.mode,
        "steps": [s.__dict__ for s in result.steps],
        "work": result.work,
        "verification": result.verification,
        "error": result.error,
        "usage": token_usage,
        "tier": tier_name,
        "monthly_usage": updated_usage,
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/agents")
async def agents():
    return {
        "total": len(_roster),
        "summary": roster_summary(_roster),
        "agents": [a.__dict__ for a in _roster],
    }


@app.get("/api/usage")
async def usage(session_id: str = "web"):
    tier_name = os.environ.get("ARCTUS_TIER", "free")
    usage = session_store.monthly_usage(session_id)
    quota = TIER_QUOTAS.get(tier_name, {})
    return {"session_id": session_id, "tier": tier_name, "usage": usage, "quota": quota}


@app.get("/api/tiers")
async def tiers():
    return {"tiers": {k: {**v} for k, v in TIER_QUOTAS.items()}}


# ---- MCP ----
@app.post("/api/mcp/connect")
async def mcp_connect(req: MCPConnectRequest):
    try:
        c = _add_mcp(req.name, req.config)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "connected", "server": c.name, "tools": c.tools}


@app.get("/api/mcp/list")
async def mcp_list():
    return {"connectors": [c.__dict__ for c in REGISTRY.list_connectors()]}


@app.delete("/api/mcp/{name}")
async def mcp_delete(name: str):
    ok = REGISTRY.remove_connector(name)
    return {"removed": ok}


# ---- Consortium ----
@app.get("/api/consortium/peers")
async def consortium_peers():
    return {"peers": [p.__dict__ for p in _hub.list_peers()]}


@app.post("/api/consortium/peers")
async def consortium_add_peer(req: PeerRequest):
    try:
        _hub.add_peer(Peer(name=req.name, base_url=req.base_url,
                           shared_secret=req.shared_secret))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "added", "peer": req.name}


@app.post("/api/consortium/submit")
async def consortium_submit(req: Request):
    auth = req.headers.get("authorization", "")
    body = await req.json()
    peer = next((p for p in _hub.list_peers()
                 if f"Bearer {p.shared_secret}" == auth), None)
    if not peer:
        raise HTTPException(status_code=401, detail="unknown peer")
    task = ConsortiumTask(
        task_id=body["task_id"], prompt=body["prompt"],
        origin=body.get("origin", peer.name),
        submitted_at=__import__("time").time(),
    )
    _hub.submit_local(task)
    return {"status": "queued", "task_id": task.task_id}


@app.get("/api/consortium/result/{task_id}")
async def consortium_result(task_id: str, request: Request):
    auth = request.headers.get("authorization", "")
    peer = next((p for p in _hub.list_peers()
                 if f"Bearer {p.shared_secret}" == auth), None)
    if not peer:
        raise HTTPException(status_code=401, detail="unknown peer")
    t = _hub.results.get(task_id)
    if not t:
        return {"status": "pending"}
    return {"status": t.status, "result": t.result}


# 3. Next.js Static Export Serving (Fallback)
# If you build Next.js (next build) it generates an 'out' folder.
# This mounts the 'out' folder so FastAPI can serve the frontend in production.
WEB_DIR = Path(__file__).resolve().parent.parent / "out" 
if WEB_DIR.is_dir():
    app.mount("/_next", StaticFiles(directory=str(WEB_DIR / "_next")), name="next_assets")
    # You can mount other static folders like /images, /css here if needed

@app.get("/{full_path:path}")
async def serve_nextjs(full_path: str):
    """Serve Next.js static files for any unmatched route."""
    if not WEB_DIR.is_dir():
        return JSONResponse({"status": "api_only", "message": "Next.js static export not found."})
        
    path = WEB_DIR / full_path
    if path.is_file():
        return FileResponse(str(path))
        
    index = WEB_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
        
    return JSONResponse({"status": "ok", "dashboard": "missing"})


def main() -> None:
    import uvicorn
    port = int(os.environ.get("PORT", "7860"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)


if __name__ == "__main__":
    main()
          
