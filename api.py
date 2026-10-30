"""FastAPI app for the LLM eval dashboard.

Serves the built React SPA (``static/dist``) and mounts the API routers.
All endpoints are JSON, read-only except the POST operations in
:mod:`routes_eval`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

import config
import db
import fonts
import routes_analysis
import routes_data
import routes_eval
import routes_export
import routes_prompts

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DIST_DIR = STATIC_DIR / "dist"

_NOT_BUILT_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>LLM Eval Dashboard</title>
<style>body{font-family:system-ui,sans-serif;padding:48px;max-width:640px;margin:auto;
color:#111;background:#fafafa}code{background:#eee;padding:2px 6px;border-radius:4px}</style>
</head><body>
<h1>Frontend not built</h1>
<p>The React app has not been built yet. Run:</p>
<p><code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code></p>
<p>Then reload this page. The JSON API is available under <code>/api</code>.</p>
</body></html>"""


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Create the schema on startup so queries work before the first ingest."""
    conn = db.connect(config.DB_PATH)
    try:
        db.init_schema(conn)
    finally:
        db.close(conn)
    yield


app = FastAPI(title="LLM Eval Dashboard", lifespan=_lifespan)
app.include_router(routes_data.router)
app.include_router(routes_analysis.router)
app.include_router(routes_eval.router)
app.include_router(routes_export.router)
app.include_router(routes_prompts.router)


@app.get("/api/fonts.css")
def font_faces():
    """@font-face rules for licensed files dropped into static/fonts/."""
    return Response(
        fonts.font_css(STATIC_DIR / "fonts"),
        media_type="text/css",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/")
def root():
    index = DIST_DIR / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse(_NOT_BUILT_HTML)


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
