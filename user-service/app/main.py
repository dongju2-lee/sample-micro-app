import os
import uvicorn
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace

from shared.logger import ServiceLogger
from shared.middleware import LoggingMiddleware
from shared.telemetry import OpenTelemetryService
import socket
import platform

# 서비스 로거 인스턴스 생성
logger = ServiceLogger(
    service_name="user-service", 
    log_level="INFO",
    hostname=socket.gethostname()
)

# OpenTelemetry 서비스 인스턴스 생성
telemetry = OpenTelemetryService("user-service")

app = FastAPI(title="User Service API")

# OpenTelemetry로 앱 계측
telemetry.instrument_app(app)

# 로깅 미들웨어 추가
app.add_middleware(LoggingMiddleware, logger=logger)

# CORS 미들웨어 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 예시 사용자 데이터
users = [
    {"id": 1, "name": "John Doe", "email": "john@example.com"},
    {"id": 2, "name": "Jane Smith", "email": "jane@example.com"}
]

@app.on_event("startup")
async def startup_event():
    """서비스 시작 시 실행되는 이벤트 핸들러"""
    # 로그에 trace_id 추가
    trace_id = telemetry.get_trace_id() or "없음"
    logger.event(
        "service_started", 
        host=socket.gethostname(),
        os=platform.platform(),
        python_version=platform.python_version(),
        workers=os.environ.get("WORKERS", "1"),
        environment=os.environ.get("ENVIRONMENT", "development"),
        trace_id=trace_id
    )
    logger.info("사용자 서비스가 시작되었습니다.")

@app.on_event("shutdown")
async def shutdown_event():
    """서비스 종료 시 실행되는 이벤트 핸들러"""
    logger.event("service_stopped")
    logger.info("사용자 서비스가 종료되었습니다.")

@app.get("/health")
async def health_check():
    """서비스 헬스 체크 엔드포인트"""
    with telemetry.create_span("health_check"):
        logger.debug("헬스 체크 요청을 받았습니다.")
        return {"status": "healthy"}

@app.get("/users")
async def get_users():
    """모든 사용자 조회 엔드포인트"""
    with telemetry.create_span("get_users_operation") as span:
        # 스팬에 속성 추가
        span.set_attribute("users.count", len(users))
        
        logger.info(f"사용자 목록 조회: {len(users)}명의 사용자가 있습니다.")
        return {"users": users}

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    """특정 사용자 조회 엔드포인트"""
    with telemetry.create_span("get_user_by_id") as span:
        # 스팬에 속성 추가
        span.set_attribute("user.id", user_id)
        
        logger.debug(f"사용자 ID {user_id}에 대한 조회 요청")
        
        try:
            # 타이머 컨텍스트 관리자를 사용하여 작업 시간 측정
            with logger.timer("get_user_by_id_operation") as timer:
                # 사용자 ID로 사용자 찾기
                user = next((u for u in users if u["id"] == user_id), None)
                
                if user:
                    span.set_attribute("user.found", True)
                    span.set_attribute("user.name", user["name"])
                    
                    logger.info(f"사용자 ID {user_id} 조회 성공", user_data=user["name"])
                    return {"user": user}
                else:
                    span.set_attribute("user.found", False)
                    
                    logger.warning(f"사용자 ID {user_id}를 찾을 수 없습니다.", user_id=user_id)
                    span.set_status(trace.StatusCode.ERROR, f"사용자 ID {user_id}를 찾을 수 없습니다.")
                    return {"error": "User not found"}, 404
        except Exception as e:
            # 예외 발생 시 스팬에 오류 정보 추가
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            
            logger.error(f"사용자 조회 중 오류 발생: {str(e)}", user_id=user_id, exc_info=True)
            raise

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True) 