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
        if self.path == "/":
            html = """<!doctype html><meta charset='utf-8'><title>B故障预警</title>
            <h1>成员 B 故障预警控制台</h1><p>提交一次设备采样查看可复现的 JSON 结果。</p>
            <form id='f'><input name='equipmentId' value='EQ-123456'><input name='temperatureC' value='100' type='number'>
            <input name='vibrationMmS' value='8' type='number'><input name='currentA' value='15' type='number'>
            <button>评估</button></form><pre id='out'></pre>
            <script>f.onsubmit=async e=>{e.preventDefault();let b=Object.fromEntries(new FormData(f));
            for(let k of ['temperatureC','vibrationMmS','currentA'])b[k]=Number(b[k]);
            out.textContent=JSON.stringify(await (await fetch('/api/v1/assessments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json(),null,2)}</script>"""
            raw = html.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        elif self.path == "/health": self._reply(200, {"status": "UP"})
        elif self.path == "/api/v1/status": self._reply(200, {"warnings": API.service.snapshot()})
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
