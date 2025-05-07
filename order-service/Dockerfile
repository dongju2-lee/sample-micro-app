FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 로그 디렉토리 생성
RUN mkdir -p /var/log/microservices/order-service && chmod -R 777 /var/log/microservices

# 서비스 코드 복사
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"] 