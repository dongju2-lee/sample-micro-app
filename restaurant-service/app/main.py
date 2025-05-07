import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace

from shared.logger import ServiceLogger
from shared.middleware import LoggingMiddleware
from shared.telemetry import OpenTelemetryService
import socket
import platform

# 서비스 로거 인스턴스 생성
logger = ServiceLogger(
    service_name="restaurant-service", 
    log_level="INFO",
    hostname=socket.gethostname()
)

# OpenTelemetry 서비스 인스턴스 생성
telemetry = OpenTelemetryService("restaurant-service")

app = FastAPI(title="Restaurant Service API")

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

# 예시 레스토랑 데이터
restaurants = [
    {"id": 1, "name": "The Italian Place", "cuisine": "Italian", "rating": 4.5},
    {"id": 2, "name": "Sushi King", "cuisine": "Japanese", "rating": 4.8},
    {"id": 3, "name": "Burger Shack", "cuisine": "American", "rating": 4.2}
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
    logger.info("레스토랑 서비스가 시작되었습니다.")

@app.on_event("shutdown")
async def shutdown_event():
    """서비스 종료 시 실행되는 이벤트 핸들러"""
    logger.event("service_stopped")
    logger.info("레스토랑 서비스가 종료되었습니다.")

@app.get("/health")
async def health_check():
    """서비스 헬스 체크 엔드포인트"""
    with telemetry.create_span("health_check"):
        logger.debug("헬스 체크 요청을 받았습니다.")
        return {"status": "healthy"}

@app.get("/restaurants")
async def get_restaurants(cuisine: str = None):
    """
    모든 레스토랑 조회 엔드포인트
    옵션: 요리 종류별 필터링
    """
    with telemetry.create_span("get_restaurants") as span:
        span.set_attribute("restaurants.count", len(restaurants))
        
        if cuisine:
            span.set_attribute("filter.cuisine", cuisine)
            logger.info(f"요리 종류별 레스토랑 조회: {cuisine}", cuisine=cuisine)
            filtered_restaurants = [r for r in restaurants if r["cuisine"].lower() == cuisine.lower()]
            span.set_attribute("restaurants.filtered_count", len(filtered_restaurants))
            logger.debug(f"{len(filtered_restaurants)}개의 레스토랑이 '{cuisine}' 카테고리에서 검색됨", count=len(filtered_restaurants))
            return {"restaurants": filtered_restaurants}
        
        logger.info(f"전체 레스토랑 목록 조회: {len(restaurants)}개의 레스토랑 반환", count=len(restaurants))
        return {"restaurants": restaurants}

@app.get("/restaurants/{restaurant_id}")
async def get_restaurant(restaurant_id: int):
    """특정 레스토랑 조회 엔드포인트"""
    with telemetry.create_span("get_restaurant_by_id") as span:
        span.set_attribute("restaurant.id", restaurant_id)
        
        logger.debug(f"레스토랑 ID {restaurant_id}에 대한 조회 요청", restaurant_id=restaurant_id)
        
        try:
            # 타이머 컨텍스트 관리자를 사용하여 작업 시간 측정
            with logger.timer("get_restaurant_by_id_operation") as timer:
                # 레스토랑 ID로 레스토랑 찾기
                restaurant = next((r for r in restaurants if r["id"] == restaurant_id), None)
                
                if restaurant:
                    span.set_attribute("restaurant.found", True)
                    span.set_attribute("restaurant.name", restaurant["name"])
                    span.set_attribute("restaurant.cuisine", restaurant["cuisine"])
                    
                    logger.info(f"레스토랑 ID {restaurant_id} 조회 성공", 
                                restaurant_id=restaurant_id, restaurant_name=restaurant["name"])
                    return {"restaurant": restaurant}
                else:
                    span.set_attribute("restaurant.found", False)
                    span.set_status(trace.StatusCode.ERROR, f"레스토랑 ID {restaurant_id}를 찾을 수 없습니다.")
                    
                    logger.warning(f"레스토랑 ID {restaurant_id}를 찾을 수 없습니다.", restaurant_id=restaurant_id)
                    raise HTTPException(status_code=404, detail="Restaurant not found")
        except HTTPException as e:
            # HTTP 예외 로깅 및 전파
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, e.detail)
            
            logger.warning(e.detail, status_code=e.status_code, restaurant_id=restaurant_id)
            raise
        except Exception as e:
            # 그 외 예외 로깅 및 전파
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            
            logger.error(f"레스토랑 조회 중 오류 발생: {str(e)}", 
                        restaurant_id=restaurant_id, exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True) 