# monitor-service 컨테이너 이미지
FROM python:3.11-slim

# .pyc 파일을 만들지 않고, 로그를 버퍼링 없이 바로 출력합니다.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./

# 보안을 위해 root 가 아닌 사용자로 실행합니다.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# 컨테이너 내부 포트 (호스트에는 공개하지 않습니다)
EXPOSE 8000

CMD ["python", "app.py"]
