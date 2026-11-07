# Auditon: 화면(React 빌드) + API(FastAPI)를 컨테이너 하나로.
# Cloudflare Pages에 화면을 따로 올려도 되고, 이 컨테이너만으로도 전체가 뜬다.

# ---- 1) 화면 빌드 ----
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ARG VITE_API_BASE=""
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

# ---- 2) API ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    AUDITON_VAR=/data
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

# 로컬 OCR(선택): docker build --build-arg WITH_OCR=1
# CPU용 torch만 설치하고, 한국어·영어 모델을 이미지에 미리 받아 둔다(실행 중 외부 다운로드 없음).
ARG WITH_OCR=0
RUN if [ "$WITH_OCR" = "1" ]; then \
      pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu \
      && pip install easyocr \
      && python -c "import easyocr; easyocr.Reader(['ko','en'], gpu=False)"; \
    fi

COPY backend/ backend/
COPY data/synthetic/tune data/synthetic/tune
COPY docs/ docs/
COPY --from=web /web/dist frontend/dist

ARG AUDITON_VERSION=dev
ENV AUDITON_VERSION=$AUDITON_VERSION
RUN useradd -m -u 1000 auditon && mkdir -p /data && chown -R auditon /data /app
USER auditon
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/health || exit 1
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
