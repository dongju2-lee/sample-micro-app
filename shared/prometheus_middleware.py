from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response
from fastapi.responses import PlainTextResponse
import time
import psutil
import os

# Prometheus 메트릭 정의
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code', 'service_name']
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint', 'service_name']
)

REQUEST_IN_PROGRESS = Gauge(
    'http_requests_in_progress',
    'HTTP requests currently in progress',
    ['service_name']
)

# 시스템 메트릭
CPU_USAGE = Gauge(
    'cpu_usage_percent',
    'CPU usage percentage',
    ['service_name']
)

MEMORY_USAGE = Gauge(
    'memory_usage_bytes',
    'Memory usage in bytes',
    ['service_name']
)

MEMORY_USAGE_PERCENT = Gauge(
    'memory_usage_percent',
    'Memory usage percentage',
    ['service_name']
)

# 데이터베이스 연결 메트릭
DB_CONNECTIONS = Gauge(
    'database_connections_active',
    'Active database connections',
    ['service_name']
)

# Redis 연결 메트릭
REDIS_OPERATIONS = Counter(
    'redis_operations_total',
    'Total Redis operations',
    ['service_name', 'operation', 'status']
)

class PrometheusMiddleware:
    def __init__(self, service_name: str):
        self.service_name = service_name
    
    async def __call__(self, request: Request, call_next):
        # 메트릭 엔드포인트는 메트릭 수집하지 않음
        if request.url.path == "/metrics":
            return await call_next(request)
        
        method = request.method
        path = request.url.path
        
        # 진행 중인 요청 수 증가
        REQUEST_IN_PROGRESS.labels(service_name=self.service_name).inc()
        
        # 요청 시작 시간 기록
        start_time = time.time()
        
        try:
            # 요청 처리
            response = await call_next(request)
            status_code = response.status_code
            
        except Exception as e:
            status_code = 500
            raise
        finally:
            # 요청 처리 시간 계산
            duration = time.time() - start_time
            
            # 메트릭 업데이트
            REQUEST_COUNT.labels(
                method=method,
                endpoint=path,
                status_code=status_code,
                service_name=self.service_name
            ).inc()
            
            REQUEST_DURATION.labels(
                method=method,
                endpoint=path,
                service_name=self.service_name
            ).observe(duration)
            
            # 진행 중인 요청 수 감소
            REQUEST_IN_PROGRESS.labels(service_name=self.service_name).dec()
            
            # 시스템 메트릭 업데이트
            self._update_system_metrics()
        
        return response
    
    def _update_system_metrics(self):
        """시스템 메트릭 업데이트"""
        try:
            # CPU 사용률
            cpu_percent = psutil.cpu_percent(interval=None)
            CPU_USAGE.labels(service_name=self.service_name).set(cpu_percent)
            
            # 메모리 사용률
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()
            
            MEMORY_USAGE.labels(service_name=self.service_name).set(memory_info.rss)
            MEMORY_USAGE_PERCENT.labels(service_name=self.service_name).set(memory_percent)
            
        except Exception as e:
            # 시스템 메트릭 수집 실패 시 로그만 남기고 계속 진행
            print(f"Failed to collect system metrics: {e}")

def get_metrics_endpoint():
    """메트릭 엔드포인트 반환"""
    async def metrics():
        return PlainTextResponse(
            generate_latest(),
            media_type=CONTENT_TYPE_LATEST
        )
    return metrics

def increment_redis_operation(service_name: str, operation: str, status: str = "success"):
    """Redis 연산 메트릭 증가"""
    REDIS_OPERATIONS.labels(
        service_name=service_name,
        operation=operation,
        status=status
    ).inc()

def set_db_connections(service_name: str, count: int):
    """데이터베이스 연결 수 설정"""
    DB_CONNECTIONS.labels(service_name=service_name).set(count) 