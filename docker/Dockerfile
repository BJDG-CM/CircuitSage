# CircuitSage 배포 이미지 (design §2.2: 전체를 이미지 하나로, ngspice 포함)
# 빌드:  docker build -f docker/Dockerfile -t circuitsage .
# 실행:  docker run -p 8000:8000 -v circuitsage-data:/data circuitsage

# --- 1단계: 프런트엔드 빌드 -------------------------------------------------
FROM node:22-slim AS webbuild
WORKDIR /build
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY web/ ./
RUN npm run build

# --- 2단계: 런타임 (Python + ngspice) ---------------------------------------
FROM python:3.12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ngspice curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY core/ core/
COPY api/ api/
COPY examples/ examples/
RUN pip install --no-cache-dir ./core ./api

COPY --from=webbuild /build/dist static/

ENV CIRCUITSAGE_STATIC_DIR=/app/static \
    CIRCUITSAGE_EXAMPLES_DIR=/app/examples \
    CIRCUITSAGE_DB=/data/circuitsage.db
RUN mkdir -p /data
VOLUME /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s \
    CMD curl -sf http://localhost:8000/api/examples > /dev/null || exit 1
CMD ["uvicorn", "circuitsage_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
