import os
import uvicorn
import httpx
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import socket
import platform
import uuid
from opentelemetry import trace

from shared.logger import ServiceLogger
from shared.middleware import LoggingMiddleware
from shared.telemetry import OpenTelemetryService

# 서비스 로거 인스턴스 생성
logger = ServiceLogger(
    service_name="order-service", 
    log_level="INFO",
    hostname=socket.gethostname()
)

# OpenTelemetry 서비스 인스턴스 생성
telemetry = OpenTelemetryService("order-service")

app = FastAPI(title="Order Service API")

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

# 서비스 URL 정의
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8001")
RESTAURANT_SERVICE_URL = os.getenv("RESTAURANT_SERVICE_URL", "http://restaurant-service:8002")

# 예시 주문 데이터
orders = [
    {"id": 1, "user_id": 1, "restaurant_id": 2, "items": ["California Roll", "Miso Soup"], "status": "completed"},
    {"id": 2, "user_id": 2, "restaurant_id": 1, "items": ["Margherita Pizza", "Tiramisu"], "status": "in-progress"}
]

# 주문 모델 정의
class OrderItem(BaseModel):
    name: str
    quantity: int
    price: Optional[float] = None

class OrderCreate(BaseModel):
    user_id: int
    restaurant_id: int
    items: List[OrderItem]

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
        user_service_url=USER_SERVICE_URL,
        restaurant_service_url=RESTAURANT_SERVICE_URL,
        trace_id=trace_id
    )
    logger.info("주문 서비스가 시작되었습니다.")

@app.on_event("shutdown")
async def shutdown_event():
    """서비스 종료 시 실행되는 이벤트 핸들러"""
    logger.event("service_stopped")
    logger.info("주문 서비스가 종료되었습니다.")

@app.get("/health")
async def health_check():
    """서비스 헬스 체크 엔드포인트"""
    with telemetry.create_span("health_check"):
        logger.debug("헬스 체크 요청을 받았습니다.")
        return {"status": "healthy"}

async def get_user(user_id: int, trace_id: str = None):
    """사용자 서비스에서 사용자 정보를 가져옵니다."""
    # 새 스팬 생성
    with telemetry.create_span("get_user_from_service", kind=trace.SpanKind.CLIENT) as span:
        span.set_attribute("user.id", user_id)
        
        logger.info(f"사용자 서비스 호출 시작: 사용자 ID {user_id}", external_call="user-service")
        
        # 헤더에 컨텍스트 전파
        headers = {}
        telemetry.inject_span_context(headers)
        
        if trace_id:
            headers["X-Trace-ID"] = trace_id
        if logger.request_id:
            headers["X-Request-ID"] = logger.request_id
        
        try:
            with logger.timer("external_call_user_service") as timer:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{USER_SERVICE_URL}/users/{user_id}", headers=headers)
                    
                    if response.status_code != 200:
                        span.set_status(trace.StatusCode.ERROR, f"사용자 서비스 호출 실패: {response.status_code}")
                        logger.warning(
                            f"사용자 서비스 호출 실패: {response.status_code}",
                            status_code=response.status_code,
                            user_id=user_id
                        )
                        return None
                    
                    user_data = response.json().get("user")
                    span.set_attribute("user.found", user_data is not None)
                    
                    if user_data:
                        span.set_attribute("user.name", user_data.get("name", ""))
                    
                    logger.info(f"사용자 서비스 호출 성공: 사용자 ID {user_id}", 
                              response_time_ms=timer.elapsed_ms)
                    return user_data
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            
            logger.error(f"사용자 서비스 호출 중 오류 발생: {str(e)}", 
                        user_id=user_id, 
                        service_url=USER_SERVICE_URL,
                        exc_info=True)
            return None

async def get_restaurant(restaurant_id: int, trace_id: str = None):
    """레스토랑 서비스에서 레스토랑 정보를 가져옵니다."""
    # 새 스팬 생성
    with telemetry.create_span("get_restaurant_from_service", kind=trace.SpanKind.CLIENT) as span:
        span.set_attribute("restaurant.id", restaurant_id)
        
        logger.info(f"레스토랑 서비스 호출 시작: 레스토랑 ID {restaurant_id}", external_call="restaurant-service")
        
        # 헤더에 컨텍스트 전파
        headers = {}
        telemetry.inject_span_context(headers)
        
        if trace_id:
            headers["X-Trace-ID"] = trace_id
        if logger.request_id:
            headers["X-Request-ID"] = logger.request_id
        
        try:
            with logger.timer("external_call_restaurant_service") as timer:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{RESTAURANT_SERVICE_URL}/restaurants/{restaurant_id}", headers=headers)
                    
                    if response.status_code != 200:
                        span.set_status(trace.StatusCode.ERROR, f"레스토랑 서비스 호출 실패: {response.status_code}")
                        logger.warning(
                            f"레스토랑 서비스 호출 실패: {response.status_code}",
                            status_code=response.status_code,
                            restaurant_id=restaurant_id
                        )
                        return None
                    
                    restaurant_data = response.json().get("restaurant")
                    span.set_attribute("restaurant.found", restaurant_data is not None)
                    
                    if restaurant_data:
                        span.set_attribute("restaurant.name", restaurant_data.get("name", ""))
                        span.set_attribute("restaurant.cuisine", restaurant_data.get("cuisine", ""))
                    
                    logger.info(f"레스토랑 서비스 호출 성공: 레스토랑 ID {restaurant_id}", 
                              response_time_ms=timer.elapsed_ms)
                    return restaurant_data
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            
            logger.error(f"레스토랑 서비스 호출 중 오류 발생: {str(e)}", 
                        restaurant_id=restaurant_id, 
                        service_url=RESTAURANT_SERVICE_URL,
                        exc_info=True)
            return None

@app.get("/orders")
async def get_orders(user_id: int = None):
    """
    모든 주문 조회 엔드포인트
    옵션: 사용자 ID별 필터링
    """
    with telemetry.create_span("get_orders") as span:
        if user_id:
            span.set_attribute("filter.user_id", user_id)
            logger.info(f"사용자 ID {user_id}의 주문 목록 조회", user_id=user_id)
            filtered_orders = [o for o in orders if o["user_id"] == user_id]
            span.set_attribute("orders.filtered_count", len(filtered_orders))
            return {"orders": filtered_orders}
        
        span.set_attribute("orders.count", len(orders))
        logger.info(f"전체 주문 목록 조회: {len(orders)}개의 주문 반환")
        return {"orders": orders}

@app.get("/orders/{order_id}")
async def get_order(order_id: int):
    """특정 주문 정보 조회 엔드포인트"""
    with telemetry.create_span("get_order_by_id") as span:
        span.set_attribute("order.id", order_id)
        
        logger.debug(f"주문 ID {order_id}에 대한 조회 요청", order_id=order_id)
        
        try:
            with logger.timer("get_order_by_id_operation") as timer:
                # 주문 ID로 주문 찾기
                order = next((o for o in orders if o["id"] == order_id), None)
                
                if not order:
                    span.set_attribute("order.found", False)
                    span.set_status(trace.StatusCode.ERROR, f"주문 ID {order_id}를 찾을 수 없습니다.")
                    
                    logger.warning(f"주문 ID {order_id}를 찾을 수 없습니다.", order_id=order_id)
                    raise HTTPException(status_code=404, detail="Order not found")
                
                span.set_attribute("order.found", True)
                span.set_attribute("order.user_id", order["user_id"])
                span.set_attribute("order.restaurant_id", order["restaurant_id"])
                span.set_attribute("order.status", order["status"])
                
                # 추적 ID 가져오기
                trace_id = telemetry.get_trace_id()
                
                # 사용자 및 레스토랑 정보 병렬 요청
                user_task = asyncio.create_task(get_user(order["user_id"], trace_id))
                restaurant_task = asyncio.create_task(get_restaurant(order["restaurant_id"], trace_id))
                
                user, restaurant = await asyncio.gather(user_task, restaurant_task)
                
                # 응답 준비
                response = {
                    "order": order,
                    "user": user,
                    "restaurant": restaurant
                }
                
                logger.info(f"주문 ID {order_id} 조회 성공", 
                           order_id=order_id, 
                           user_id=order["user_id"],
                           restaurant_id=order["restaurant_id"],
                           processing_time_ms=timer.elapsed_ms)
                
                return response
        except HTTPException as e:
            # HTTP 예외 로깅 및 전파
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, e.detail)
            
            logger.warning(e.detail, status_code=e.status_code, order_id=order_id)
            raise
        except Exception as e:
            # 그 외 예외 로깅 및 전파
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            
            logger.error(f"주문 조회 중 오류 발생: {str(e)}", 
                        order_id=order_id, exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/orders", status_code=201)
async def create_order(order_data: OrderCreate):
    """새 주문 생성 엔드포인트"""
    with telemetry.create_span("create_order") as span:
        span.set_attribute("order.user_id", order_data.user_id)
        span.set_attribute("order.restaurant_id", order_data.restaurant_id)
        span.set_attribute("order.items_count", len(order_data.items))
        
        logger.info("새 주문 생성 요청", user_id=order_data.user_id, restaurant_id=order_data.restaurant_id)
        
        try:
            with logger.timer("create_order_operation") as timer:
                # 현재 추적 ID 가져오기
                trace_id = telemetry.get_trace_id()
                
                # 사용자 및 레스토랑 정보 병렬 요청으로 검증
                user_task = asyncio.create_task(get_user(order_data.user_id, trace_id))
                restaurant_task = asyncio.create_task(get_restaurant(order_data.restaurant_id, trace_id))
                
                user, restaurant = await asyncio.gather(user_task, restaurant_task)
                
                # 사용자나 레스토랑이 존재하지 않으면 오류 반환
                if not user:
                    span.set_attribute("validation.error", "user_not_found")
                    span.set_status(trace.StatusCode.ERROR, f"사용자 ID {order_data.user_id}가 존재하지 않습니다.")
                    
                    logger.warning(f"주문 생성 실패: 사용자 ID {order_data.user_id}가 존재하지 않습니다.", 
                                 user_id=order_data.user_id)
                    raise HTTPException(status_code=404, detail="User not found")
                
                if not restaurant:
                    span.set_attribute("validation.error", "restaurant_not_found")
                    span.set_status(trace.StatusCode.ERROR, f"레스토랑 ID {order_data.restaurant_id}가 존재하지 않습니다.")
                    
                    logger.warning(f"주문 생성 실패: 레스토랑 ID {order_data.restaurant_id}가 존재하지 않습니다.", 
                                 restaurant_id=order_data.restaurant_id)
                    raise HTTPException(status_code=404, detail="Restaurant not found")
                
                # 새 주문 ID는 현재 주문 목록 중 가장 높은 ID + 1
                new_order_id = max(o["id"] for o in orders) + 1 if orders else 1
                
                # 새 주문 생성
                new_order = {
                    "id": new_order_id,
                    "user_id": order_data.user_id,
                    "restaurant_id": order_data.restaurant_id,
                    "items": [{"name": item.name, "quantity": item.quantity, "price": item.price} for item in order_data.items],
                    "status": "pending"
                }
                
                # 주문 목록에 추가
                orders.append(new_order)
                
                span.set_attribute("order.id", new_order_id)
                span.set_attribute("order.status", "pending")
                
                logger.info(f"주문 생성 성공: ID {new_order_id}", 
                           order_id=new_order_id,
                           user_id=order_data.user_id,
                           restaurant_id=order_data.restaurant_id,
                           items_count=len(order_data.items),
                           processing_time_ms=timer.elapsed_ms)
                
                # 주문 정보 반환
                return {"order": new_order}
        except HTTPException as e:
            # HTTP 예외 로깅 및 전파
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, e.detail)
            
            logger.warning(f"주문 생성 실패: {e.detail}", 
                          status_code=e.status_code, 
                          user_id=order_data.user_id,
                          restaurant_id=order_data.restaurant_id)
            raise
        except Exception as e:
            # 그 외 예외 로깅 및 전파
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            
            logger.error(f"주문 생성 중 오류 발생: {str(e)}", 
                        user_id=order_data.user_id,
                        restaurant_id=order_data.restaurant_id,
                        exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True) 