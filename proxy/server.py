"""
Tavily API Proxy — FastAPI 主服务
"""
import os
import time
import httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

import database as db
from key_pool import pool

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
TAVILY_API_BASE = "https://api.tavily.com"

app = FastAPI(title="Tavily API Proxy")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
http_client = httpx.AsyncClient(timeout=60)


# ═══ Auth helpers ═══

def verify_admin(request: Request):
    auth = request.headers.get("Authorization", "")
    password = request.headers.get("X-Admin-Password", "")
    if auth == f"Bearer {ADMIN_PASSWORD}" or password == ADMIN_PASSWORD:
        return True
    raise HTTPException(status_code=401, detail="Unauthorized")


def extract_token(request: Request, body: dict = None):
    """从请求中提取用户 token"""
    # 1. Authorization header
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    # 2. body 中的 api_key 字段
    if body and body.get("api_key"):
        return body["api_key"]
    return None


# ═══ 启动 ═══

@app.on_event("startup")
def startup():
    db.init_db()


# ═══ 代理端点 ═══

@app.post("/api/search")
@app.post("/api/extract")
async def proxy_tavily(request: Request):
    body = await request.json()
    endpoint = request.url.path.replace("/api/", "")  # search or extract

    # 验证 token
    token_value = extract_token(request, body)
    if not token_value:
        raise HTTPException(status_code=401, detail="Missing API token")

    token_row = db.get_token_by_value(token_value)
    if not token_row:
        raise HTTPException(status_code=401, detail="Invalid token")

    # 检查配额
    ok, reason = db.check_quota(
        token_row["id"],
        token_row["hourly_limit"],
        token_row["daily_limit"],
        token_row["monthly_limit"],
    )
    if not ok:
        raise HTTPException(status_code=429, detail=reason)

    # 从 key pool 取 key
    key_info = pool.get_next_key()
    if not key_info:
        raise HTTPException(status_code=503, detail="No available API keys")

    # 替换 api_key 并转发
    body["api_key"] = key_info["key"]
    start = time.time()
    try:
        resp = await http_client.post(f"{TAVILY_API_BASE}/{endpoint}", json=body)
        latency = int((time.time() - start) * 1000)
        success = resp.status_code == 200

        # 记录结果
        pool.report_result(key_info["id"], success)
        db.log_usage(token_row["id"], key_info["id"], endpoint, int(success), latency)

        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as e:
        latency = int((time.time() - start) * 1000)
        pool.report_result(key_info["id"], False)
        db.log_usage(token_row["id"], key_info["id"], endpoint, 0, latency)
        raise HTTPException(status_code=502, detail=str(e))


# ═══ 控制台 ═══

@app.get("/console", response_class=HTMLResponse)
async def console(request: Request):
    return templates.TemplateResponse("console.html", {"request": request})


# ═══ 管理 API ═══

@app.get("/api/stats")
async def stats(request: Request, _=Depends(verify_admin)):
    all_stats = db.get_usage_stats()
    tokens = [dict(t) for t in db.get_all_tokens()]
    for t in tokens:
        t["stats"] = db.get_usage_stats(t["id"])
    keys = db.get_all_keys()
    return {
        "overview": all_stats,
        "tokens": tokens,
        "keys_total": len(keys),
        "keys_active": sum(1 for k in keys if k["active"]),
    }


@app.get("/api/keys")
async def list_keys(request: Request, _=Depends(verify_admin)):
    keys = [dict(k) for k in db.get_all_keys()]
    for k in keys:
        # 脱敏显示
        raw = k["key"]
        k["key_masked"] = raw[:8] + "***" + raw[-4:] if len(raw) > 12 else raw
    return {"keys": keys}


@app.post("/api/keys")
async def add_keys(request: Request, _=Depends(verify_admin)):
    body = await request.json()
    if "file" in body:
        count = db.import_keys_from_text(body["file"])
        pool.reload()
        return {"imported": count}
    elif "key" in body:
        db.add_key(body["key"], body.get("email", ""))
        pool.reload()
        return {"ok": True}
    raise HTTPException(status_code=400, detail="Provide 'key' or 'file'")


@app.delete("/api/keys/{key_id}")
async def remove_key(key_id: int, _=Depends(verify_admin)):
    db.delete_key(key_id)
    pool.reload()
    return {"ok": True}


@app.put("/api/keys/{key_id}/toggle")
async def toggle_key(key_id: int, request: Request, _=Depends(verify_admin)):
    body = await request.json()
    db.toggle_key(key_id, body.get("active", 1))
    pool.reload()
    return {"ok": True}


@app.get("/api/tokens")
async def list_tokens(request: Request, _=Depends(verify_admin)):
    tokens = [dict(t) for t in db.get_all_tokens()]
    for t in tokens:
        t["stats"] = db.get_usage_stats(t["id"])
    return {"tokens": tokens}


@app.post("/api/tokens")
async def create_token(request: Request, _=Depends(verify_admin)):
    body = await request.json()
    token = db.create_token(body.get("name", ""))
    return {"token": dict(token)}


@app.delete("/api/tokens/{token_id}")
async def remove_token(token_id: int, _=Depends(verify_admin)):
    db.delete_token(token_id)
    return {"ok": True}
