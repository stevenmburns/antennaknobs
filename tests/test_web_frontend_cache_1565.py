"""Regression test for antennaknobs#1565.

The workbench mounts its built frontend with plain `StaticFiles(html=True)`,
which sends ETag/Last-Modified and no Cache-Control at all. Browsers apply
heuristic freshness to that, so once the workbench took a fixed port
(#1540) a browser could keep showing an old cached index.html for
127.0.0.1:8000 forever, silently talking a stale bundle's request shapes to
the current API (two 400s on first load in the field report).

This does not use `server.app` (its frontend mount is gated on a built
`src/antennaknobs/web/static`, absent in a source checkout) or the
module-scoped `client` fixture in test_web_server.py — it mounts a throwaway
bundle onto a fresh FastAPI instance via `server._mount_frontend`, the hook
the fix added for exactly this.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from antennaknobs.web import server


def _client_for(tmp_path: Path) -> TestClient:
    static_dir = tmp_path / "static"
    (static_dir / "assets").mkdir(parents=True)
    (static_dir / "index.html").write_text("<html>stub</html>")
    (static_dir / "assets" / "index-deadbeef.js").write_text("console.log('stub')")

    app = FastAPI()
    server._mount_frontend(app, static_dir)
    return TestClient(app)


def test_root_and_index_html_carry_no_cache(tmp_path: Path):
    client = _client_for(tmp_path)

    for path in ("/", "/index.html"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache", path
        # ETag/Last-Modified stay so a revalidation is still a cheap 304.
        assert "etag" in response.headers, path


def test_hashed_assets_are_not_forced_to_revalidate(tmp_path: Path):
    client = _client_for(tmp_path)

    response = client.get("/assets/index-deadbeef.js")
    assert response.status_code == 200
    assert "no-cache" not in response.headers.get("cache-control", "")
