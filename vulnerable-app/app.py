"""
LinkLens : 링크를 모아 두고 미리보기를 제공하는 작은 웹 서비스입니다.

교육용 실습 앱입니다. 로컬 Docker 환경에서만 실행하세요.

제공 기능
---------
- POST /preview          : 링크 미리보기
- GET  /api/links        : 저장된 링크 목록
- GET  /api/links/<id>   : 저장된 링크 상세
- POST /api/url-check    : URL 형식 검사
"""

import json
import logging
import re
import time
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, render_template, request

REQUEST_TIMEOUT_SECONDS = 3
MAX_CONTENT_BYTES = 4096
MAX_URL_LENGTH = 2048

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [linklens] %(message)s",
)
# Flask 개발 서버의 기본 접근 로그 대신 아래 로그만 보이도록 합니다.
logging.getLogger("werkzeug").setLevel(logging.WARNING)

app = Flask(__name__)

# 저장된 링크 (저장 당시의 스냅샷입니다. 상세 보기는 이 값만 돌려줍니다.)
SAVED_LINKS = {
    1: {
        "id": 1,
        "url": "http://content-service:8000/public",
        "title": "공개 공지",
        "description": "서비스 공지 페이지.",
        "saved_at": "2026-09-01T09:00:00Z",
    },
    2: {
        "id": 2,
        "url": "http://content-service:8000/articles/99",
        "title": "지난 캠페인 안내",
        "description": "이전 캠페인 소개 페이지.",
        "saved_at": "2026-09-03T14:20:00Z",
    },
    3: {
        "id": 3,
        "url": "http://content-service:8000/legacy",
        "title": "이전 랜딩 페이지",
        "description": "구버전 랜딩 페이지.",
        "saved_at": "2026-09-10T11:05:00Z",
    },
    4: {
        "id": 4,
        "url": "http://content-service:8000/notice",
        "title": "운영 공지",
        "description": "서비스 운영 관련 공지사항.",
        "saved_at": "2026-09-20T09:10:00Z",
    },
}

TITLE_PATTERN = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def describe_target(url):
    """로그용으로 URL의 목적지(호스트/포트/경로)를 나눠 보여 줍니다."""
    try:
        parsed = urlparse(url)
        return "scheme=%s host=%s port=%s path=%s" % (
            parsed.scheme or "-",
            parsed.hostname or "-",
            parsed.port or "-",
            parsed.path or "/",
        )
    except ValueError:
        return "unparsable"


def extract_title(body_text, content_type):
    """HTML 이면 <title>, JSON 이면 title 필드를 미리보기 제목으로 씁니다."""
    if "html" in content_type:
        match = TITLE_PATTERN.search(body_text)
        if match:
            return match.group(1).strip()
    if "json" in content_type:
        try:
            data = json.loads(body_text)
            if isinstance(data, dict) and isinstance(data.get("title"), str):
                return data["title"]
        except ValueError:
            pass
    return None


def build_content(response, content_type, body_text):
    """Content-Type 이 JSON 이면 파싱해 객체로, 그 외에는 문자열로 content 를 만듭니다.

    반환: (content_value, title)
    - JSON: content_value 는 dict/list 등 파싱된 객체 (중첩 필드가 그대로 유지됨)
    - 그 외: content_value 는 문자열, 제목은 extract_title 로 추출
    """
    if "json" in content_type.lower() and len(response.content) <= 65536:
        try:
            data = response.json()
        except ValueError:
            return body_text, extract_title(body_text, content_type)
        title = data.get("title") if isinstance(data, dict) and isinstance(data.get("title"), str) else None
        return data, title
    return body_text, extract_title(body_text, content_type)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.post("/preview")
def preview():
    """링크 미리보기: 입력받은 URL의 내용을 가져와 제목과 본문 일부를 보여 줍니다."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON body is required"}), 400

    url = data.get("url")
    if not isinstance(url, str) or not url.strip():
        return jsonify({"error": "URL is required"}), 400
    url = url.strip()

    app.logger.info("preview requested url=%s", url)

    started = time.monotonic()
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except requests.RequestException as error:
        # app_returned : 앱이 사용자에게 돌려주는 HTTP 상태 (여기서는 502).
        # upstream_status=- : 대상 서버 응답을 받지 못함.
        app.logger.info(
            "outbound GET %s -> upstream_status=- app_returned=502 result=failed (%s)",
            describe_target(url),
            type(error).__name__,
        )
        return jsonify({"requested_url": url, "fetched": False, "error": "Could not fetch this URL"}), 502

    elapsed_ms = int((time.monotonic() - started) * 1000)
    content_type = response.headers.get("Content-Type", "")
    body_text = response.content[:MAX_CONTENT_BYTES].decode("utf-8", errors="replace")
    content_value, title = build_content(response, content_type, body_text)

    # app_returned=200 : 대상 서버가 4xx/5xx 를 줘도 앱 자신은 200 으로 응답합니다.
    # 그래서 app_returned 와 upstream_status 가 다를 수 있고, 이 차이를 로그로 확인할 수 있습니다.
    app.logger.info(
        "outbound GET %s -> upstream_status=%s app_returned=200 bytes=%s elapsed_ms=%s",
        describe_target(url),
        response.status_code,
        len(response.content),
        elapsed_ms,
    )

    return jsonify(
        {
            "requested_url": url,
            "fetched": True,
            "status_code": response.status_code,
            "content_type": content_type,
            "title": title,
            "content": content_value,
        }
    )


@app.get("/api/links")
def list_links():
    """저장된 링크 목록입니다."""
    return jsonify({"links": [
        {"id": link["id"], "title": link["title"]} for link in SAVED_LINKS.values()
    ]})


@app.get("/api/links/<int:link_id>")
def link_detail(link_id):
    """저장된 링크 상세: 저장 당시의 스냅샷을 돌려줍니다."""
    link = SAVED_LINKS.get(link_id)
    app.logger.info("saved link detail id=%s found=%s", link_id, link is not None)
    if link is None:
        return jsonify({"error": "Link not found"}), 404
    return jsonify(link)


@app.post("/api/url-check")
def url_check():
    """URL 형식 검사: URL을 구성요소로 나눠서 보여 줍니다."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON body is required"}), 400

    url = data.get("url")
    if not isinstance(url, str) or not url.strip():
        return jsonify({"valid": False, "problems": ["URL is empty"]})
    url = url.strip()

    problems = []
    components = {}
    if len(url) > MAX_URL_LENGTH:
        problems.append("URL is too long")
    try:
        parsed = urlparse(url)
        components = {
            "scheme": parsed.scheme,
            "host": parsed.hostname,
            "port": parsed.port,
            "path": parsed.path,
            "query": parsed.query,
        }
        if parsed.scheme not in ("http", "https"):
            problems.append("Scheme should be http or https")
        if not parsed.hostname:
            problems.append("Host is missing")
    except ValueError:
        problems.append("URL could not be parsed")

    app.logger.info("url-check url=%s valid=%s", url, not problems)
    return jsonify({"url": url, "valid": not problems, "components": components, "problems": problems})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
