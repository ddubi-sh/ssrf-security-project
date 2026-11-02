"""
monitor-service : LinkLens 가 저장한 링크의 상태를 주기적으로 점검하는 내부 서비스입니다.

- 컨테이너 내부 8000번 포트, 호스트에는 공개하지 않습니다.
- 아래 데이터는 모두 실습용 가상 운영 데이터입니다. 실제 계정·키·개인정보가 아닙니다.
"""

import logging

from flask import Flask, jsonify, request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [monitor-service] %(message)s",
)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

app = Flask(__name__)

# 조회 가능한 점검 리포트 (실습용 가상 데이터). 그 밖의 id 는 404 입니다.
REPORTS = {
    "2026-09-28": {
        "report_id": "2026-09-28",
        "generated_at": "2026-09-28T02:00:00Z",
        "window": "최근 24시간",
        "summary": {"checked": 128, "reachable": 124, "failed": 4},
        "recent_failures": [
            {"target": "content-service", "path": "/articles/99", "status": 404},
            {"target": "content-service", "path": "/legacy", "status": 500},
        ],
        "worker_nodes": ["monitor-a", "monitor-b"],
        "note": "내부 진단용 데이터",
    },
}
REPORTS["latest"] = REPORTS["2026-09-28"]


@app.after_request
def log_request(response):
    """요청 경로, 요청을 보낸 컨테이너 주소, 응답 상태를 남깁니다."""
    if request.path != "/health":
        app.logger.info(
            "%s %s from=%s -> %s", request.method, request.path, request.remote_addr, response.status_code
        )
    return response


@app.get("/")
def index():
    """서비스 소개. 상세 상태는 /status 로 안내만 합니다."""
    return jsonify(
        {
            "service": "monitor-service",
            "description": "내부 링크 상태 점검 서비스",
            "info": "운영 상태는 /status 에서 확인할 수 있습니다",
        }
    )


@app.get("/status")
def status():
    """일반 운영 상태입니다. 상세 리포트는 여기서 조회 경로만 안내합니다."""
    return jsonify(
        {
            "service": "monitor-service",
            "state": "running",
            "queue_depth": 3,
            "last_run": "2026-09-28T02:00:00Z",
            "reports": {"path": "/reports/{id}", "latest_id": "2026-09-28"},
            "note": "상세 점검 리포트는 reports 경로에서 조회합니다",
        }
    )


@app.get("/reports/<report_id>")
def report(report_id):
    """특정 점검 리포트입니다. (실습용 가상 운영 데이터)"""
    item = REPORTS.get(report_id)
    if item is None:
        return jsonify({"service": "monitor-service", "error": "리포트를 찾을 수 없습니다"}), 404
    return jsonify(item)


@app.errorhandler(404)
def not_found(_error):
    return jsonify({"service": "monitor-service", "error": "Not found"}), 404


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
