"""Loopback-only staging entry points; refuse production configuration."""
import json
import os
from pathlib import Path

ROOT = Path("/tmp/apexretail-phase7f-runtime")
CONFIG = ROOT / "runtime.json"


def settings():
    data = json.loads(CONFIG.read_text())
    from sqlalchemy.engine import make_url
    url = make_url(data["database_url"])
    if (data["environment"] != "phase7f-staging"
        or data["database"] != "apexretail_phase7f_acceptance"
        or data["source"] != "/tmp/apexpos-phase7f"
        or url.drivername != "postgresql+asyncpg" or url.username != "apex_user"
        or url.host is not None or url.port is not None
        or url.database != data["database"]
        or dict(url.query) != {"host": str(ROOT / "socket"), "port": "55437"}
        or data["api_environment"].get("APP_ENV") != "staging"):
        raise RuntimeError("Refusing non-staging configuration")
    return data


def api_app():
    data = settings()
    # Never inherit production credentials/provider variables or a production .env.
    os.environ.clear()
    os.environ.update(data["api_environment"])
    os.environ["DATABASE_URL"] = data["database_url"]
    from app.main import app
    from fastapi.middleware.cors import CORSMiddleware
    for middleware in app.user_middleware:
        if middleware.cls is CORSMiddleware:
            middleware.kwargs["allow_origins"] = ["https://localhost:18770", "https://localhost", "capacitor://localhost"]

    @app.get("/api/staging-identity")
    async def identity():
        from app.db.session import SessionLocal
        from sqlalchemy import text
        async with SessionLocal() as db:
            row = (await db.execute(text("SELECT current_database() database,current_user role,(SELECT version_num FROM alembic_version) revision"))).mappings().one()
            if row["database"] != data["database"] or row["role"] != "apex_user":
                raise RuntimeError("Unexpected staging database identity")
            return {**dict(row), "environment": "phase7f-staging", "source_commit": data["source_commit"]}
    return app


def gateway_app():
    data = settings()
    import httpx
    from fastapi import FastAPI, Request, HTTPException
    from starlette.responses import Response, FileResponse
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    roots = [ROOT / "web/pos", ROOT / "web/backoffice"]

    @app.middleware("http")
    async def safety_headers(request, call_next):
        if request.headers.get("host") not in {"localhost:18770", "127.0.0.1:18770"}:
            return Response("Staging accepts loopback hosts only", status_code=403)
        response = await call_next(request)
        response.headers["X-Apex-Environment"] = "phase7f-staging"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def proxy(path: str, request: Request):
        if len(await request.body()) > 10 * 1024 * 1024:
            raise HTTPException(413, "Staging request too large")
        headers = {k: v for k, v in request.headers.items() if k.lower() not in {"connection", "content-length", "transfer-encoding", "host"}}
        headers.update({"host": "localhost:18770", "x-forwarded-proto": "https"})
        async with httpx.AsyncClient(trust_env=False, timeout=60) as client:
            upstream = await client.request(request.method, "http://127.0.0.1:18771/api/" + path,
                params=request.query_params, headers=headers, content=await request.body())
        return Response(upstream.content, status_code=upstream.status_code,
            headers={k: v for k, v in upstream.headers.items() if k.lower() not in {"connection", "content-length", "transfer-encoding", "content-encoding"}})

    @app.get("/{path:path}")
    async def frontend(path: str):
        relative = path.removeprefix("backoffice/") if path.startswith("backoffice/") else path
        selected = roots[1] if path == "backoffice" or path.startswith("backoffice/") else roots[0]
        if path.startswith("assets/"):
            for root in roots:
                target = (root / path).resolve()
                if target.is_relative_to(root) and target.is_file(): return FileResponse(target)
            raise HTTPException(404)
        target = (selected / relative).resolve()
        if not target.is_relative_to(selected): raise HTTPException(404)
        return FileResponse(target if target.is_file() else selected / "index.html")
    return app
