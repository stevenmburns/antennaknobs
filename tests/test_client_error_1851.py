"""Crash reports from the hosted app's browsers (AK#1851).

POST /client-error logs one ``client-error:`` line carrying the message, the
React component stack and the app version, scrubbed of any URL query (the
``?deck=`` link carries a visitor's whole deck) and bounded. Hosted only: a
local workbench answers 404 and reports nowhere. Rate-limited per client and
fleet-wide; the client's address keys the limit and is never written.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from antennaknobs.web import hosting, server

DECK_LINK = "https://app.antennaknobs.dev/?deck=eJzLSM3JyQcABiwCFQ&v=1#top"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(server.app)


@pytest.fixture()
def hosted(monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", True)
    monkeypatch.setattr(server, "_CLIENT_ERRORS", hosting.ClientErrorSink())


def _lines(caplog) -> list[dict]:
    out = []
    for rec in caplog.records:
        msg = rec.getMessage()
        if msg.startswith("client-error: "):
            out.append(json.loads(msg[len("client-error: ") :]))
    return out


def _post(client, payload, ip="203.0.113.7"):
    return client.post(
        "/client-error",
        content=json.dumps(payload),
        headers={"Fly-Client-IP": ip, "Content-Type": "application/json"},
    )


def test_local_workbench_answers_404_and_logs_nothing(client, caplog, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", False)
    caplog.set_level(logging.WARNING, logger="antennaknobs.client_error")
    r = _post(client, {"message": "boom", "version": "1.0"})
    assert r.status_code == 404
    assert _lines(caplog) == []
    assert client.get("/capabilities").json()["client_error_reports"] is False


def test_hosted_logs_one_line_with_three_scrubbed_fields(client, hosted, caplog):
    caplog.set_level(logging.WARNING, logger="antennaknobs.client_error")
    r = _post(
        client,
        {
            "message": f"TypeError: x is undefined at {DECK_LINK}",
            "component_stack": f"\n    at DesignSession ({DECK_LINK})\n    at App",
            "version": "0.96.0",
            # Anything else is dropped unread.
            "url": DECK_LINK,
            "user_agent": "Mozilla/5.0",
            "deck": "GW 1 11 0 0 0 0 0 10 0.001",
        },
        ip="198.51.100.23",
    )
    assert r.status_code == 204
    (line,) = _lines(caplog)
    assert set(line) == {"message", "component_stack", "version"}
    assert line["version"] == "0.96.0"
    assert line["message"] == (
        "TypeError: x is undefined at https://app.antennaknobs.dev/"
    )
    assert "DesignSession (https://app.antennaknobs.dev/)" in line["component_stack"]
    text = caplog.text
    for leak in ("eJzLSM3JyQcABiwCFQ", "198.51.100.23", "Mozilla", "GW 1 11"):
        assert leak not in text


def test_fields_are_bounded_and_a_bad_version_is_unknown(client, hosted, caplog):
    caplog.set_level(logging.WARNING, logger="antennaknobs.client_error")
    r = _post(
        client,
        {
            "message": "m" * 5000,
            "component_stack": "s" * 9000,
            "version": "1.0; rm -rf /",
        },
    )
    assert r.status_code == 204
    (line,) = _lines(caplog)
    assert len(line["message"]) == hosting.MESSAGE_MAX + 1  # + the ellipsis
    assert len(line["component_stack"]) == hosting.STACK_MAX + 1
    assert line["version"] == "unknown"


def test_oversized_body_is_refused_unread(client, hosted, caplog):
    caplog.set_level(logging.WARNING, logger="antennaknobs.client_error")
    r = _post(client, {"message": "x" * (hosting.BODY_MAX + 1)})
    assert r.status_code == 413
    assert _lines(caplog) == []


def test_rate_limited_per_client_and_not_across_clients(client, hosted, caplog):
    caplog.set_level(logging.WARNING, logger="antennaknobs.client_error")
    codes = [
        _post(client, {"message": f"e{i}"}, ip="203.0.113.1").status_code
        for i in range(hosting.PER_CLIENT_PER_MIN + 2)
    ]
    assert codes == [204] * hosting.PER_CLIENT_PER_MIN + [429, 429]
    # Another visitor is not held to the first one's budget.
    assert _post(client, {"message": "other"}, ip="203.0.113.2").status_code == 204
    assert len(_lines(caplog)) == hosting.PER_CLIENT_PER_MIN + 1


def test_fleet_wide_budget_bounds_the_log(caplog):
    caplog.set_level(logging.WARNING, logger="antennaknobs.client_error")
    sink = hosting.ClientErrorSink(per_client=100, total=3)
    logged = [sink.report({"message": str(i)}, f"10.0.0.{i}") for i in range(5)]
    assert logged == [True, True, True, False, False]
    assert len(_lines(caplog)) == 3


def test_capabilities_says_hosted_reports(client, hosted):
    assert client.get("/capabilities").json()["client_error_reports"] is True


@pytest.mark.parametrize(
    "text, want",
    [
        ("at https://h.dev/app?deck=ABC&v=1 (x)", "at https://h.dev/app (x)"),
        ("GET /deck?deck=ABC failed", "GET /deck failed"),
        ("open //h/x#frag now", "open //h/x now"),
        ("deck=ZZZ", "deck=…"),
        ("is it 5? yes", "is it 5? yes"),
    ],
)
def test_scrub_matches_the_frontend(text, want):
    # The same cases as errorBoundary.test.tsx's scrubReportText: the two
    # scrubbers agree, so a report is as clean whichever side cut it.
    assert hosting.scrub(text) == want
