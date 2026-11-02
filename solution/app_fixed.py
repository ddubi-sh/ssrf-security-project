"""
solution/app_fixed.py : LinkLens 의 SSRF 취약점을 수정한 완성본입니다.

사용 방법
---------
막히는 경우에만 참고하세요. 이 파일의 내용을 vulnerable-app/app.py 에 복사한 뒤
`docker compose up --build` 로 다시 빌드하면 수정본으로 실습할 수 있습니다.

핵심 아이디어
-------------
"위험한 것을 골라 막는" 차단 목록(blocklist)이 아니라,
"허용된 것만 통과시키는" 허용 목록(allowlist) 방식으로 검증합니다.
문자열 검색(`"localhost" in url`)이 아니라 urlparse() 로 URL을
구성요소(스킴/호스트/포트/경로 등)로 나눠서 검사합니다.

수정 대상은 /preview 하나입니다.
- /api/url-check, /api/links/<id> 는 서버가 외부로 요청하지 않으므로 그대로 둡니다.
- 화면 기능(3종)과 로그 형식은 취약 버전과 동일하게 유지합니다.
"""

import json
import logging
import re
import time
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, render_template, request

# ----------------------------------------------------------------------------
# 허용 목록 : LinkLens 가 미리보기를 허용하는 것은 content-service 의 공개 콘텐츠뿐입니다.
# 내부 monitor-service 로는 애초에 요청이 나가지 않습니다.
# ----------------------------------------------------------------------------
ALLOWED_SCHEME = "http"
ALLOWED_HOST = "content-service"
ALLOWED_PORT = 8000
ALLOWED_PATHS = ("/public", "/articles/1", "/articles/2", "/notice", "/status")

REQUEST_TIMEOUT_SECONDS = 3
MAX_CONTENT_BYTES = 4096
MAX_URL_LENGTH = 2048

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [linklens] %(message)s",
)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

app = Flask(__name__)

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
    """JSON 응답은 파싱해 객체로, 그 외에는 문자열로 content 를 만듭니다. 반환: (content, title)"""
    if "json" in content_type.lower() and len(response.content) <= 65536:
        try:
            data = response.json()
        except ValueError:
            return body_text, extract_title(body_text, content_type)
        title = data.get("title") if isinstance(data, dict) and isinstance(data.get("title"), str) else None
        return data, title
    return body_text, extract_title(body_text, content_type)


def validate_url(url):
    """
    URL이 허용 목록 조건을 모두 만족하는지 검사합니다.

    반환값:
        (True, None)            - 검증 통과
        (False, "이유 문자열")   - 검증 실패

    실패 이유는 학생이 이해할 정도만 알려 주고,
    내부 구조(허용 호스트/포트)를 자세히 노출하지 않습니다.
    """
    # 1) 타입 검사
    if not isinstance(url, str):
        return False, "URL must be a string"
    url = url.strip()
    if not url:
        return False, "URL is required"

    # 2) 길이 제한 (파싱 전에 비정상적으로 긴 입력 차단)
    if len(url) > MAX_URL_LENGTH:
        return False, "URL is too long"

    # 3) 파싱 (형식이 잘못되면 ValueError 가능)
    try:
        parsed = urlparse(url)
        port = parsed.port          # 포트 형식 오류 시 ValueError
        hostname = parsed.hostname  # 소문자 정규화된 호스트
    except ValueError:
        return False, "URL could not be parsed"

    # 4) 스킴 : http 만 허용 (file/gopher/ftp/dict 등 거부)
    if parsed.scheme != ALLOWED_SCHEME:
        return False, "URL scheme is not allowed"

    # 5) 사용자정보(user:pass@) 거부 : http://content-service@monitor-service/ 눈속임 차단
    if parsed.username is not None or parsed.password is not None:
        return False, "URL must not contain user information"

    # 6) 호스트 : 정확히 허용된 호스트만 (monitor-service 등 내부 호스트 거부)
    if hostname != ALLOWED_HOST:
        return False, "URL host is not allowed"

    # 7) 포트 : 정확히 허용된 포트만 (생략 시 80 → 거부)
    if port != ALLOWED_PORT:
        return False, "URL port is not allowed"

    # 8) 경로 : 허용된 경로 목록만 (monitor-service 의 /reports/... 등 내부 경로 거부)
    if parsed.path not in ALLOWED_PATHS:
        return False, "URL path is not allowed"

    # 9) query : 이번 실습에서는 불필요하므로 거부
    if parsed.query:
        return False, "URL must not contain a query string"

    # 10) fragment(#...) : 서버 요청에는 불필요하므로 거부
    if parsed.fragment:
        return False, "URL must not contain a fragment"

    return True, None


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.post("/preview")
def preview():
    """사용자가 입력한 URL을 '검증한 뒤에만' 서버가 대신 요청합니다."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON body is required"}), 400

    url = data.get("url")

    # ------------------------------------------------------------------
    # 검증 : 통과하지 못하면 서버는 아무 요청도 보내지 않습니다.
    # (Sink 인 requests.get() 에 도달하기 전에 막는 것이 핵심)
    # ------------------------------------------------------------------
    is_valid, reason = validate_url(url)
    if not is_valid:
        app.logger.info(
            "blocked preview url=%s reason=%s app_returned=400", url, reason
        )
        return jsonify({"error": "Blocked by URL policy", "reason": reason}), 400

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
    return jsonify({"links": [
        {"id": link["id"], "title": link["title"]} for link in SAVED_LINKS.values()
    ]})


@app.get("/api/links/<int:link_id>")
def link_detail(link_id):
    link = SAVED_LINKS.get(link_id)
    app.logger.info("saved link detail id=%s found=%s", link_id, link is not None)
    if link is None:
        return jsonify({"error": "Link not found"}), 404
    return jsonify(link)


@app.post("/api/url-check")
def url_check():
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
