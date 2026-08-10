# ---------- stage 1: build the React console ----------
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

# ---------- stage 2: runtime ----------
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY nexus/ nexus/
COPY config/ config/
COPY static/ static/
COPY --from=frontend /build/dist frontend/dist
EXPOSE 8611
CMD ["uvicorn", "nexus.main:app", "--host", "0.0.0.0", "--port", "8611"]
