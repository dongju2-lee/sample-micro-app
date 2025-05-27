FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# OpenTelemetry 관련 패키지 설치
RUN pip install opentelemetry-distro opentelemetry-exporter-otlp
RUN opentelemetry-bootstrap -a install

# 로그 디렉토리 생성
RUN mkdir -p /var/log/microservices/order-service && chmod -R 777 /var/log/microservices

# 서비스 코드 복사
COPY . .

EXPOSE 8000

# OpenTelemetry 자동계측 실행
CMD ["opentelemetry-instrument", "--service_name", "order-service", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"] 