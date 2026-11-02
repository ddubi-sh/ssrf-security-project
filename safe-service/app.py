"""
content-service : LinkLens 가 미리보기로 가져오는 공개 콘텐츠 서비스 역할입니다.

- 컨테이너 내부 8000번 포트, 호스트에는 공개하지 않습니다.
"""

import logging

from flask import Flask, jsonify, request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [content-service] %(message)s",
)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

app = Flask(__name__)

ARTICLES = {
    1: {
        "title": "Getting started with LinkLens",
        "body": "Save links, preview them, and share collections with your team.",
    },
    2: {
        "title": "Release notes",
        "body": "Improved preview titles and faster saved link lookups.",
    },
}


@app.after_request
def log_request(response):
    """어떤 경로로 요청이 들어와 어떤 상태로 응답했는지 남깁니다."""
    if request.path != "/health":
        app.logger.info(
            "%s %s from=%s -> %s", request.method, request.path, request.remote_addr, response.status_code
        )
    return response


@app.get("/public")
def public_resource():
    return jsonify(
        {
            "service": "content-service",
            "title": "Public notice",
            "message": "This is an allowed public resource.",
        }
    )


@app.get("/articles/<int:article_id>")
def article(article_id):
    item = ARTICLES.get(article_id)
    if item is None:
        return jsonify({"service": "content-service", "error": "Article not found"}), 404
    return jsonify({"service": "content-service", **item})


@app.get("/notice")
def notice():
    """운영 공지. 저장된 링크로도 등록되어 있어 미리보기로 열어볼 수 있습니다."""
    return jsonify(
        {
            "service": "content-service",
            "title": "Service notice",
            "body": (
                "저장된 링크의 상태는 내부 모니터링 서비스가 주기적으로 점검합니다. "
                "링크 점검 담당 서비스: monitor-service. "
                "각 서비스의 운영 상태는 /status 에서 확인할 수 있습니다."
            ),
            "updated_at": "2026-09-20T09:00:00Z",
        }
    )


@app.get("/status")
def status():
    """이 콘텐츠 서비스 자신의 상태입니다."""
    return jsonify({"service": "content-service", "status": "ok", "uptime": "3d", "version": "2.1.0"})


@app.get("/legacy")
def legacy():
    """예전 랜딩 페이지. 지금은 오류를 반환합니다. (실습용)"""
    return jsonify({"service": "content-service", "error": "내부 오류로 페이지를 불러오지 못했습니다"}), 500


@app.errorhandler(404)
def not_found(_error):
    return jsonify({"service": "content-service", "error": "Not found"}), 404


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
