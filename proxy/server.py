"""
多服务 API Proxy — FastAPI 主服务
"""
import asyncio
import json
import os
import time
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

import database as db
from key_pool import pool

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
TAVILY_API_BASE = "https://api.tavily.com"
FIRECRAWL_API_BASE = "https://api.firecrawl.dev"
USAGE_SYNC_TTL_SECONDS = int(os.environ.get("USAGE_SYNC_TTL_SECONDS", "300"))
USAGE_SYNC_CONCURRENCY = max(1, int(os.environ.get("USAGE_SYNC_CONCURRENCY", "4")))
SERVICE_LABELS = {
    "tavily": "Tavily",
    "firecrawl": "Firecrawl",
}

app = FastAPI(title="Tavily / Firecrawl API Proxy")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
http_client = httpx.AsyncClient(timeout=60)


def get_admin_password():
    return db.get_setting("admin_password", ADMIN_PASSWORD)


def get_service(service_value, default="tavily"):
    try:
        return db.normalize_service(service_value or default)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ═══ Auth helpers ═══

def verify_admin(request: Request):
    auth = request.headers.get("Authorization", "")
    password = request.headers.get("X-Admin-Password", "")
    pwd = get_admin_password()
    if auth == f"Bearer {pwd}" or password == pwd:
        return True
    raise HTTPException(status_code=401, detail="Unauthorized")


def extract_token(request: Request, body: dict = None):
    """从请求中提取代理 token。"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    if body and body.get("api_key"):
        return body["api_key"]
    return None


def get_token_row_or_401(token_value, service):
    if not token_value:
        raise HTTPException(status_code=401, detail="Missing API token")
    token_row = db.get_token_by_value(token_value)
    if not token_row or token_row["service"] != service:
        raise HTTPException(status_code=401, detail="Invalid token")
    return token_row


def parse_usage_number(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def compute_remaining(limit_value, used_value):
    if limit_value is None or used_value is None:
        return None
    return max(0, limit_value - used_value)


def parse_sync_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def is_usage_sync_stale(key_row, ttl_seconds=USAGE_SYNC_TTL_SECONDS):
    synced_at = parse_sync_time(key_row.get("usage_synced_at"))
    if not synced_at:
        return True
    return (datetime.now(timezone.utc) - synced_at).total_seconds() >= ttl_seconds


async def fetch_remote_usage_tavily(key_value):
    resp = await http_client.get(
        f"{TAVILY_API_BASE}/usage",
        headers={"Authorization": f"Bearer {key_value}"},
    )
    if resp.status_code != 200:
        detail = ""
        try:
            payload = resp.json()
            detail = payload.get("detail") or payload.get("message") or ""
        except Exception:
            detail = resp.text.strip()
        detail = detail[:200] if detail else f"HTTP {resp.status_code}"
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return resp.json()


async def fetch_remote_usage_firecrawl(key_value):
    headers = {"Authorization": f"Bearer {key_value}"}
    current_resp, history_resp = await asyncio.gather(
        http_client.get(f"{FIRECRAWL_API_BASE}/v2/team/credit-usage", headers=headers),
        http_client.get(
            f"{FIRECRAWL_API_BASE}/v2/team/credit-usage/historical",
            params={"byApiKey": "true"},
            headers=headers,
        ),
    )

    for resp in (current_resp, history_resp):
        if resp.status_code != 200:
            detail = resp.text.strip()[:200] or f"HTTP {resp.status_code}"
            raise HTTPException(status_code=resp.status_code, detail=detail)

    return {
        "current": current_resp.json(),
        "historical": history_resp.json(),
    }


def normalize_usage_payload(service, payload):
    if service == "tavily":
        key_info = payload.get("key") or {}
        account_info = payload.get("account") or {}

        key_used = parse_usage_number(key_info.get("usage"))
        key_limit = parse_usage_number(key_info.get("limit"))
        account_used = parse_usage_number(account_info.get("plan_usage"))
        account_limit = parse_usage_number(account_info.get("plan_limit"))

        return {
            "key_used": key_used,
            "key_limit": key_limit,
            "key_remaining": compute_remaining(key_limit, key_used),
            "account_plan": (account_info.get("current_plan") or "").strip(),
            "account_used": account_used,
            "account_limit": account_limit,
            "account_remaining": compute_remaining(account_limit, account_used),
        }

    current_data = (payload.get("current") or {}).get("data") or {}
    history_periods = (payload.get("historical") or {}).get("periods") or []
    if history_periods:
        latest_period = max(
            history_periods,
            key=lambda item: ((item.get("endDate") or ""), (item.get("startDate") or "")),
        )
        current_period_rows = [
            item for item in history_periods
            if item.get("startDate") == latest_period.get("startDate")
            and item.get("endDate") == latest_period.get("endDate")
        ]
    else:
        current_period_rows = []

    account_remaining = parse_usage_number(current_data.get("remainingCredits"))
    plan_credits = parse_usage_number(current_data.get("planCredits"))
    account_used = sum(parse_usage_number(item.get("creditsUsed")) or 0 for item in current_period_rows)
    account_limit = None
    if account_remaining is not None:
        account_limit = account_remaining + account_used

    if plan_credits is None:
        account_plan = "Firecrawl"
    else:
        account_plan = f"Plan credits {plan_credits}"

    return {
        "key_used": None,
        "key_limit": None,
        "key_remaining": None,
        "account_plan": account_plan,
        "account_used": account_used,
        "account_limit": account_limit,
        "account_remaining": account_remaining,
    }


async def sync_usage_for_key_row(key_row):
    service = key_row.get("service") or "tavily"
    try:
        if service == "firecrawl":
            payload = await fetch_remote_usage_firecrawl(key_row["key"])
        else:
            payload = await fetch_remote_usage_tavily(key_row["key"])

        normalized = normalize_usage_payload(service, payload)
        db.update_key_remote_usage(
            key_row["id"],
            key_used=normalized["key_used"],
            key_limit=normalized["key_limit"],
            key_remaining=normalized["key_remaining"],
            account_plan=normalized["account_plan"],
            account_used=normalized["account_used"],
            account_limit=normalized["account_limit"],
            account_remaining=normalized["account_remaining"],
        )
        return {"key_id": key_row["id"], "status": "synced"}
    except HTTPException as exc:
        db.update_key_remote_usage_error(key_row["id"], exc.detail)
        return {"key_id": key_row["id"], "status": "error", "detail": exc.detail}
    except Exception as exc:
        db.update_key_remote_usage_error(key_row["id"], str(exc))
        return {"key_id": key_row["id"], "status": "error", "detail": str(exc)}


async def sync_usage_cache(force=False, key_id=None, service=None):
    rows = []
    if key_id is not None:
        row = db.get_key_by_id(key_id)
        if row and (service is None or row["service"] == service):
            rows = [dict(row)]
    else:
        rows = [dict(row) for row in db.get_all_keys(service)]

    if not rows:
        return {"requested": 0, "synced": 0, "skipped": 0, "errors": 0}

    to_sync = rows if force else [row for row in rows if is_usage_sync_stale(row)]
    if not to_sync:
        return {"requested": len(rows), "synced": 0, "skipped": len(rows), "errors": 0}

    semaphore = asyncio.Semaphore(USAGE_SYNC_CONCURRENCY)

    async def worker(row):
        async with semaphore:
            return await sync_usage_for_key_row(row)

    results = await asyncio.gather(*(worker(row) for row in to_sync))
    synced = sum(1 for item in results if item["status"] == "synced")
    errors = sum(1 for item in results if item["status"] == "error")
    return {
        "requested": len(rows),
        "synced": synced,
        "skipped": len(rows) - len(to_sync),
        "errors": errors,
    }


def build_real_quota_summary(keys):
    synced_keys = [
        key for key in keys
        if key.get("usage_key_used") is not None or key.get("usage_account_used") is not None
    ]
    total_limit = 0
    total_used = 0
    total_remaining = 0
    key_level_count = 0
    account_fallback_count = 0
    accounted_groups = set()
    latest_sync = None
    for key in synced_keys:
        key_limit = key.get("usage_key_limit")
        key_used = key.get("usage_key_used")
        account_limit = key.get("usage_account_limit")
        account_used = key.get("usage_account_used")

        if key_limit is not None and key_used is not None:
            total_limit += key_limit
            total_used += key_used
            total_remaining += key.get("usage_key_remaining") or compute_remaining(key_limit, key_used) or 0
            key_level_count += 1
        elif account_limit is not None and account_used is not None:
            group_id = (key.get("email") or "").strip().lower() or f"key:{key.get('id')}"
            if group_id not in accounted_groups:
                accounted_groups.add(group_id)
                total_limit += account_limit
                total_used += account_used
                total_remaining += key.get("usage_account_remaining") or compute_remaining(account_limit, account_used) or 0
                account_fallback_count += 1

        synced_at = parse_sync_time(key.get("usage_synced_at"))
        if synced_at and (latest_sync is None or synced_at > latest_sync):
            latest_sync = synced_at

    error_count = sum(1 for key in keys if (key.get("usage_sync_error") or "").strip())
    return {
        "synced_keys": len(synced_keys),
        "total_keys": len(keys),
        "total_limit": total_limit,
        "total_used": total_used,
        "total_remaining": total_remaining,
        "error_keys": error_count,
        "last_synced_at": latest_sync.isoformat() if latest_sync else "",
        "key_level_count": key_level_count,
        "account_fallback_count": account_fallback_count,
    }


def mask_key_rows(keys):
    for key in keys:
        raw = key["key"]
        key["key_masked"] = raw[:8] + "***" + raw[-4:] if len(raw) > 12 else raw
    return keys


async def build_service_dashboard(service):
    service = get_service(service)
    sync_result = await sync_usage_cache(force=False, service=service)
    overview = db.get_usage_stats(service=service)
    tokens = [dict(token) for token in db.get_all_tokens(service)]
    for token in tokens:
        token["stats"] = db.get_usage_stats(token_id=token["id"], service=service)
    keys = mask_key_rows([dict(key) for key in db.get_all_keys(service)])
    active_keys = [key for key in keys if key["active"]]
    return {
        "service": service,
        "label": SERVICE_LABELS[service],
        "overview": overview,
        "tokens": tokens,
        "keys": keys,
        "keys_total": len(keys),
        "keys_active": len(active_keys),
        "real_quota": build_real_quota_summary(active_keys),
        "usage_sync": sync_result,
    }


def build_forward_headers(request, real_key):
    skip_headers = {
        "authorization",
        "content-length",
        "host",
        "x-admin-password",
    }
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in skip_headers
    }
    headers["Authorization"] = f"Bearer {real_key}"
    return headers


async def parse_json_body(request):
    raw_body = await request.body()
    if not raw_body:
        return raw_body, None
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" not in content_type:
        return raw_body, None
    try:
        return raw_body, json.loads(raw_body.decode("utf-8"))
    except Exception:
        return raw_body, None


def forward_raw_response(resp):
    """尽量保留上游返回格式，避免把非 JSON Firecrawl 响应再包一层。"""
    content_type = resp.headers.get("content-type", "")
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=content_type or None,
    )


# ═══ 启动 ═══

@app.on_event("startup")
def startup():
    db.init_db()


# ═══ Tavily 代理端点 ═══

@app.post("/api/search")
@app.post("/api/extract")
async def proxy_tavily(request: Request):
    body = await request.json()
    endpoint = request.url.path.replace("/api/", "")

    token_value = extract_token(request, body)
    token_row = get_token_row_or_401(token_value, "tavily")

    ok, reason = db.check_quota(
        token_row["id"],
        token_row["hourly_limit"],
        token_row["daily_limit"],
        token_row["monthly_limit"],
        service="tavily",
    )
    if not ok:
        raise HTTPException(status_code=429, detail=reason)

    key_info = pool.get_next_key("tavily")
    if not key_info:
        raise HTTPException(status_code=503, detail="No available API keys")

    body["api_key"] = key_info["key"]
    start = time.time()
    try:
        resp = await http_client.post(f"{TAVILY_API_BASE}/{endpoint}", json=body)
        latency = int((time.time() - start) * 1000)
        success = resp.status_code == 200
        pool.report_result("tavily", key_info["id"], success)
        db.log_usage(token_row["id"], key_info["id"], endpoint, int(success), latency, service="tavily")
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as exc:
        latency = int((time.time() - start) * 1000)
        pool.report_result("tavily", key_info["id"], False)
        db.log_usage(token_row["id"], key_info["id"], endpoint, 0, latency, service="tavily")
        raise HTTPException(status_code=502, detail=str(exc))


# ═══ Firecrawl 代理端点 ═══

@app.api_route("/firecrawl/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_firecrawl(path: str, request: Request):
    raw_body, body_json = await parse_json_body(request)
    token_value = extract_token(request, body_json)
    token_row = get_token_row_or_401(token_value, "firecrawl")

    ok, reason = db.check_quota(
        token_row["id"],
        token_row["hourly_limit"],
        token_row["daily_limit"],
        token_row["monthly_limit"],
        service="firecrawl",
    )
    if not ok:
        raise HTTPException(status_code=429, detail=reason)

    key_info = pool.get_next_key("firecrawl")
    if not key_info:
        raise HTTPException(status_code=503, detail="No available API keys")

    forward_content = raw_body
    if body_json is not None and "api_key" in body_json:
        body_json["api_key"] = key_info["key"]
        forward_content = json.dumps(body_json).encode("utf-8")

    start = time.time()
    try:
        resp = await http_client.request(
            request.method,
            f"{FIRECRAWL_API_BASE}/{path}",
            params=dict(request.query_params),
            content=forward_content if request.method != "GET" else None,
            headers=build_forward_headers(request, key_info["key"]),
        )
        latency = int((time.time() - start) * 1000)
        success = resp.status_code < 400
        pool.report_result("firecrawl", key_info["id"], success)
        db.log_usage(token_row["id"], key_info["id"], path, int(success), latency, service="firecrawl")
        content_type = resp.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        return forward_raw_response(resp)
    except Exception as exc:
        latency = int((time.time() - start) * 1000)
        pool.report_result("firecrawl", key_info["id"], False)
        db.log_usage(token_row["id"], key_info["id"], path, 0, latency, service="firecrawl")
        raise HTTPException(status_code=502, detail=str(exc))


# ═══ 控制台 ═══

@app.get("/", response_class=HTMLResponse)
async def console(request: Request):
    return templates.TemplateResponse("console.html", {"request": request})


# ═══ 管理 API ═══

@app.get("/api/stats")
async def stats(request: Request, _=Depends(verify_admin)):
    tavily_stats, firecrawl_stats = await asyncio.gather(
        build_service_dashboard("tavily"),
        build_service_dashboard("firecrawl"),
    )
    return {
        "services": {
            "tavily": tavily_stats,
            "firecrawl": firecrawl_stats,
        }
    }


@app.get("/api/keys")
async def list_keys(request: Request, _=Depends(verify_admin)):
    service = request.query_params.get("service")
    keys = mask_key_rows([dict(key) for key in db.get_all_keys(service)])
    return {"keys": keys}


@app.post("/api/usage/sync")
async def sync_usage(request: Request, _=Depends(verify_admin)):
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    service = get_service(body.get("service"), default="tavily")
    force = bool(body.get("force", True))
    key_id = body.get("key_id")
    result = await sync_usage_cache(force=force, key_id=key_id, service=service)
    keys = [dict(key) for key in db.get_all_keys(service)]
    active_keys = [key for key in keys if key["active"]]
    return {
        "ok": True,
        "service": service,
        "result": result,
        "real_quota": build_real_quota_summary(active_keys),
    }


@app.post("/api/keys")
async def add_keys(request: Request, _=Depends(verify_admin)):
    body = await request.json()
    service = get_service(body.get("service"), default="tavily")
    if "file" in body:
        count = db.import_keys_from_text(body["file"], service=service)
        pool.reload(service)
        return {"imported": count, "service": service}
    if "key" in body:
        db.add_key(body["key"], body.get("email", ""), service=service)
        pool.reload(service)
        return {"ok": True, "service": service}
    raise HTTPException(status_code=400, detail="Provide 'key' or 'file'")


@app.delete("/api/keys/{key_id}")
async def remove_key(key_id: int, _=Depends(verify_admin)):
    key_row = db.get_key_by_id(key_id)
    db.delete_key(key_id)
    if key_row:
        pool.reload(key_row["service"])
    return {"ok": True}


@app.put("/api/keys/{key_id}/toggle")
async def toggle_key(key_id: int, request: Request, _=Depends(verify_admin)):
    body = await request.json()
    db.toggle_key(key_id, body.get("active", 1))
    key_row = db.get_key_by_id(key_id)
    if key_row:
        pool.reload(key_row["service"])
    return {"ok": True}


@app.get("/api/tokens")
async def list_tokens(request: Request, _=Depends(verify_admin)):
    service = request.query_params.get("service")
    tokens = [dict(token) for token in db.get_all_tokens(service)]
    for token in tokens:
        token["stats"] = db.get_usage_stats(token_id=token["id"], service=token["service"])
    return {"tokens": tokens}


@app.post("/api/tokens")
async def create_token(request: Request, _=Depends(verify_admin)):
    body = await request.json()
    service = get_service(body.get("service"), default="tavily")
    token = db.create_token(body.get("name", ""), service=service)
    return {"token": dict(token)}


@app.delete("/api/tokens/{token_id}")
async def remove_token(token_id: int, _=Depends(verify_admin)):
    db.delete_token(token_id)
    return {"ok": True}


@app.put("/api/password")
async def change_password(request: Request, _=Depends(verify_admin)):
    body = await request.json()
    new_pwd = body.get("password", "").strip()
    if not new_pwd or len(new_pwd) < 4:
        raise HTTPException(status_code=400, detail="Password too short (min 4)")
    db.set_setting("admin_password", new_pwd)
    return {"ok": True}
