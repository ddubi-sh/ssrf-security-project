/* ============================================================================
   LinkLens - 화면 동작 스크립트

   화면에는 URL과 관련된 기능이 3개 있습니다. 각 기능은 서로 다른 형태의
   같은 출처(same-origin) 요청 하나만 보냅니다.

     1) 링크 미리보기     : POST /preview          (JSON 본문 {"url": ...})
     2) 저장된 링크 상세   : GET  /api/links, /api/links/<id>  (경로 기반 GET)
     3) URL 형식 검사     : POST /api/url-check    (JSON 본문 {"url": ...})

   공통 원칙
   - 입력값이 비어 있는지만 확인합니다. 호스트/IP/포트/스킴은 검사하지 않습니다.
     (그 검증은 서버의 몫입니다.)
   - 브라우저가 대상 주소로 직접 나가지 않고, 항상 위의 로컬 API만 호출합니다.
   - 응답은 innerHTML 이 아니라 textContent 로만 출력합니다.
   ========================================================================== */

"use strict";

var PREVIEW_ENDPOINT = "/preview";
var LINKS_ENDPOINT = "/api/links";
var URL_CHECK_ENDPOINT = "/api/url-check";

// 브라우저 쪽 요청이 영원히 끝나지 않는 것을 막기 위한 상한 시간(ms)입니다.
var CLIENT_TIMEOUT_MS = 15000;

function byId(id) {
  return document.getElementById(id);
}

/** 지정한 밀리초 뒤에 abort 되는 fetch. AbortController 가 없으면 그냥 fetch. */
function fetchWithTimeout(url, options) {
  options = options || {};
  if (typeof AbortController !== "function") {
    return fetch(url, options);
  }
  var controller = new AbortController();
  options.signal = controller.signal;
  var timeoutId = window.setTimeout(function () {
    controller.abort();
  }, CLIENT_TIMEOUT_MS);
  return fetch(url, options).then(
    function (response) {
      window.clearTimeout(timeoutId);
      return response;
    },
    function (error) {
      window.clearTimeout(timeoutId);
      throw error;
    }
  );
}

/**
 * content 렌더링.
 * - 객체/배열이면 보기 좋게 들여쓴 JSON 으로 표시합니다.
 * - 문자열이면 그대로 텍스트로 표시합니다.
 */
function formatBody(content) {
  if (content === null || content === undefined) {
    return "";
  }
  if (typeof content === "object") {
    try {
      return JSON.stringify(content, null, 2);
    } catch (error) {
      return String(content);
    }
  }
  return String(content);
}

/* ==========================================================================
   기능 1 : 링크 미리보기  (POST /preview)
   ========================================================================== */

var previewForm = byId("preview-form");
var urlInput = byId("url-input");
var previewButton = byId("preview-button");
var loadingBox = byId("loading");
var errorMessage = byId("error-message");
var resultCard = byId("result-card");
var resultTitle = byId("result-title");
var resultUrl = byId("result-url");
var resultBody = byId("result-body");

var isPreviewInFlight = false;

function setPreviewLoading(isLoading) {
  isPreviewInFlight = isLoading;
  previewButton.disabled = isLoading;
  loadingBox.hidden = !isLoading;
}

function showPreviewError(message) {
  errorMessage.textContent = message;
  errorMessage.hidden = false;
}

function showPreviewResult(data) {
  var title = typeof data.title === "string" ? data.title : "";
  if (title) {
    resultTitle.textContent = title;
    resultTitle.hidden = false;
  } else {
    resultTitle.textContent = "";
    resultTitle.hidden = true;
  }
  resultUrl.textContent = typeof data.requested_url === "string" ? data.requested_url : "";
  resultBody.textContent = formatBody(data.content);
  resultCard.hidden = false;
}

function sendPreviewRequest(url) {
  return fetchWithTimeout(PREVIEW_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: url })
  })
    .then(function (response) {
      return response.json().catch(function () {
        return null;
      });
    })
    .then(function (data) {
      if (!data || typeof data !== "object" || typeof data.status_code !== "number") {
        showPreviewError("이 URL의 미리보기를 불러오지 못했습니다. 주소를 확인하고 다시 시도하세요.");
        return;
      }
      errorMessage.hidden = true;
      showPreviewResult(data);
    })
    .catch(function () {
      showPreviewError("서버에 연결하지 못했습니다. 다시 시도하세요.");
    })
    .then(function () {
      setPreviewLoading(false);
    });
}

previewForm.addEventListener("submit", function (event) {
  event.preventDefault();
  if (isPreviewInFlight) {
    return;
  }
  var url = urlInput.value.trim();
  if (url === "") {
    resultCard.hidden = true;
    showPreviewError("URL을 입력하세요.");
    urlInput.focus();
    return;
  }
  errorMessage.hidden = true;
  resultCard.hidden = true;
  setPreviewLoading(true);
  sendPreviewRequest(url);
});

/* ==========================================================================
   기능 2 : 저장된 링크 상세  (GET /api/links, GET /api/links/<id>)
   ========================================================================== */

var savedList = byId("saved-links");
var savedError = byId("saved-error");
var savedDetail = byId("saved-detail");
var detailTitle = byId("detail-title");
var detailUrl = byId("detail-url");
var detailDescription = byId("detail-description");
var detailSavedAt = byId("detail-saved-at");

function showSavedError(message) {
  savedError.textContent = message;
  savedError.hidden = false;
}

function renderSavedDetail(link) {
  detailTitle.textContent = typeof link.title === "string" ? link.title : "";
  detailUrl.textContent = typeof link.url === "string" ? link.url : "";
  detailDescription.textContent = typeof link.description === "string" ? link.description : "";
  detailSavedAt.textContent = typeof link.saved_at === "string" ? link.saved_at : "";
  savedDetail.hidden = false;
}

function loadSavedDetail(id) {
  savedError.hidden = true;
  fetchWithTimeout(LINKS_ENDPOINT + "/" + encodeURIComponent(id))
    .then(function (response) {
      return response.json().catch(function () {
        return null;
      });
    })
    .then(function (link) {
      if (!link || typeof link !== "object" || typeof link.id !== "number") {
        showSavedError("이 저장된 링크를 열지 못했습니다.");
        return;
      }
      renderSavedDetail(link);
    })
    .catch(function () {
      showSavedError("서버에 연결하지 못했습니다. 다시 시도하세요.");
    });
}

function renderSavedList(links) {
  // 항상 textContent + createElement 로만 그립니다.
  while (savedList.firstChild) {
    savedList.removeChild(savedList.firstChild);
  }
  links.forEach(function (link) {
    var li = document.createElement("li");
    var button = document.createElement("button");
    button.type = "button";
    button.className = "saved-item";
    button.textContent = typeof link.title === "string" ? link.title : "(제목 없음)";
    button.addEventListener("click", function () {
      loadSavedDetail(link.id);
    });
    li.appendChild(button);
    savedList.appendChild(li);
  });
}

function loadSavedList() {
  fetchWithTimeout(LINKS_ENDPOINT)
    .then(function (response) {
      return response.json().catch(function () {
        return null;
      });
    })
    .then(function (data) {
      if (!data || !Array.isArray(data.links)) {
        showSavedError("저장된 링크를 불러오지 못했습니다.");
        return;
      }
      renderSavedList(data.links);
    })
    .catch(function () {
      showSavedError("서버에 연결하지 못했습니다. 다시 시도하세요.");
    });
}

/* ==========================================================================
   기능 3 : URL 형식 검사  (POST /api/url-check)
   ========================================================================== */

var checkForm = byId("check-form");
var checkInput = byId("check-input");
var checkButton = byId("check-button");
var checkError = byId("check-error");
var checkResult = byId("check-result");
var checkValid = byId("check-valid");
var checkScheme = byId("check-scheme");
var checkHost = byId("check-host");
var checkPort = byId("check-port");
var checkPath = byId("check-path");
var checkProblems = byId("check-problems");

var isCheckInFlight = false;

function showCheckError(message) {
  checkError.textContent = message;
  checkError.hidden = false;
}

function renderCheckResult(data) {
  var comp = data.components || {};
  function show(v) {
    return v === null || v === undefined || v === "" ? "—" : String(v);
  }
  checkValid.textContent = data.valid ? "예" : "아니오";
  checkScheme.textContent = show(comp.scheme);
  checkHost.textContent = show(comp.host);
  checkPort.textContent = show(comp.port);
  checkPath.textContent = show(comp.path);
  var problems = Array.isArray(data.problems) ? data.problems : [];
  checkProblems.textContent = problems.length ? problems.join(", ") : "없음";
  checkResult.hidden = false;
}

checkForm.addEventListener("submit", function (event) {
  event.preventDefault();
  if (isCheckInFlight) {
    return;
  }
  var url = checkInput.value.trim();
  if (url === "") {
    checkResult.hidden = true;
    showCheckError("URL을 입력하세요.");
    checkInput.focus();
    return;
  }
  checkError.hidden = true;
  checkResult.hidden = true;
  isCheckInFlight = true;
  checkButton.disabled = true;

  fetchWithTimeout(URL_CHECK_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: url })
  })
    .then(function (response) {
      return response.json().catch(function () {
        return null;
      });
    })
    .then(function (data) {
      if (!data || typeof data !== "object" || typeof data.valid !== "boolean") {
        showCheckError("이 URL을 확인하지 못했습니다. 다시 시도하세요.");
        return;
      }
      checkError.hidden = true;
      renderCheckResult(data);
    })
    .catch(function () {
      showCheckError("서버에 연결하지 못했습니다. 다시 시도하세요.");
    })
    .then(function () {
      isCheckInFlight = false;
      checkButton.disabled = false;
    });
});

/* ==========================================================================
   초기 로드
   ========================================================================== */

loadSavedList();
