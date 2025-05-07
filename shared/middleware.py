import time
import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from .logger import ServiceLogger

class LoggingMiddleware(BaseHTTPMiddleware):
    """
    요청과 응답을 로깅하는 FastAPI 미들웨어
    
    요청 시작/종료 시간, 응답 상태 코드, 처리 시간 등을 로깅합니다.
    """
    
    def __init__(self, app: ASGIApp, logger: ServiceLogger):
        super().__init__(app)
        self.logger = logger
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 요청 ID 생성 (헤더에 있으면 사용, 없으면 새로 생성)
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        self.logger.set_request_id(request_id)
        
        # 요청 정보 로깅
        start_time = time.time()
        self.logger.info(
            f"Request started: {request.method} {request.url.path}",
            method=request.method,
            path=request.url.path,
            query_params=dict(request.query_params),
            client_host=request.client.host if request.client else None,
            headers={k: v for k, v in request.headers.items() if k.lower() not in ["authorization", "cookie"]}
        )
        
        try:
            # 요청 처리
            response = await call_next(request)
            
            # 응답 정보와 처리 시간 로깅
            process_time = time.time() - start_time
            status_code = response.status_code
            
            log_method = self.logger.info if status_code < 400 else self.logger.warning
            log_method(
                f"Request completed: {request.method} {request.url.path} - {status_code}",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                process_time_ms=round(process_time * 1000, 2)
            )
            
            # 응답 헤더에 요청 ID 추가
            response.headers["X-Request-ID"] = request_id
            return response
            
        except Exception as exc:
            # 예외 발생 시 로깅
            process_time = time.time() - start_time
            self.logger.error(
                f"Request failed: {request.method} {request.url.path}",
                exc_info=exc,
                method=request.method,
                path=request.url.path,
                process_time_ms=round(process_time * 1000, 2)
            )
            raise 