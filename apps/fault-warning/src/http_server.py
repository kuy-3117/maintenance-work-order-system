"""Self-contained HTTP API for the fault-warning service (no parent package imports)."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .application.service import WarningService
from .domain.evaluation import HealthInput, RuleBasedHealthEvaluator
from .domain.models import MaintenanceResult, RiskLevel


class Api:
    def __init__(self) -> None:
        self.service = WarningService()
        self.evaluator = RuleBasedHealthEvaluator()

    def assess(self, body: dict) -> dict:
        sample = HealthInput(body["equipmentId"], float(body["temperatureC"]),
                             float(body["vibrationMmS"]), float(body["currentA"]))
        warning = self.service.record_assessment(self.evaluator.evaluate(sample), event_id=body.get("eventId"))
        if warning is None:
            return {"warning": None, "event": None}
        return {"warning": warning.__dict__, "event": self.service.warning_raised_event(warning.warning_id, body.get("traceId", "local"))}

    def conclusion(self, body: dict) -> dict:
        p = body["payload"] if "payload" in body else body
        warning_id = p.get("warningId")
        if not warning_id:
            raise ValueError("warningId 不能为空")
        result = MaintenanceResult(p["result"])
        warning = self.service.apply_maintenance_conclusion(warning_id=warning_id, root_cause=p["rootCause"],
                                                            result=result, effective=bool(p["effective"]))
        return {"warningId": warning.warning_id, "status": warning.status.value}


API = Api()


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, value: dict) -> None:
        raw = json.dumps(value, ensure_ascii=False, default=str).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health": self._reply(200, {"status": "UP"})
        else: self._reply(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            if self.path == "/api/v1/assessments": self._reply(201, API.assess(body))
            elif self.path == "/api/v1/maintenance-conclusions": self._reply(200, API.conclusion(body))
            elif self.path == "/api/v1/warnings": self._reply(201, API.assess(body))
            else: self._reply(404, {"error": "not_found"})
        except KeyError as exc:
            if self.path == "/api/v1/maintenance-conclusions": self._reply(404, {"error": "warning_not_found", "message": str(exc)})
            else: self._reply(400, {"error": "missing_field", "field": str(exc)})
        except (ValueError, json.JSONDecodeError) as exc: self._reply(400, {"error": "invalid_request", "message": str(exc)})

    def log_message(self, *_: object) -> None: return


def serve() -> None:
    port = int(os.getenv("B_SERVICE_PORT", os.getenv("APP_PORT", "8102")))
    ThreadingHTTPServer((os.getenv("B_SERVICE_HOST", "0.0.0.0"), port), Handler).serve_forever()


if __name__ == "__main__": serve()
