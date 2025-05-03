import os
import json
import random
import time
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Enum as SQLEnum, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import httpx
import redis
from fastapi.security import OAuth2PasswordBearer, HTTPBearer

# 환경변수 설정
DB_URL = os.getenv("DB_URL", "postgresql://order:pass@localhost:5432/order")
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://localhost:8001")
RESTAURANT_SERVICE_URL = os.getenv("RESTAURANT_SERVICE_URL", "http://localhost:8002")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/2")

# OAuth2 설정 (Swagger UI에 Authorize 버튼 표시용)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{USER_SERVICE_URL}/login")
security = HTTPBearer()

# 데이터베이스 설정
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Redis 설정
redis_client = redis.from_url(REDIS_URL)

# Helper 함수
def get_redis_client():
    return redis_client

# 결제 실패율 설정 전역 변수
payment_fail_percent = 0

# JSON에서 datetime을 처리하기 위한 인코더
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super(DateTimeEncoder, self).default(obj)

# 주문 상태 Enum
class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    FAILED = "failed"

# 주문 모델
class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    total_price = Column(Float)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    address = Column(String)
    phone = Column(String)
    payment_status = Column(String, default="pending")

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    menu_id = Column(Integer)
    quantity = Column(Integer)
    price = Column(Float)
    name = Column(String)

# Pydantic 모델
class OrderItemCreate(BaseModel):
    menu_id: int = Field(..., description="메뉴 ID", example=1)
    quantity: int = Field(..., description="주문 수량", example=2, gt=0)

class OrderCreate(BaseModel):
    items: List[OrderItemCreate] = Field(..., description="주문 아이템 목록")
    address: str = Field(..., description="배달 주소", example="서울시 강남구 123-45")
    phone: str = Field(..., description="연락처", example="010-1234-5678")

class OrderItemResponse(BaseModel):
    id: int = Field(..., description="주문 아이템 ID")
    menu_id: int = Field(..., description="메뉴 ID")
    quantity: int = Field(..., description="주문 수량")
    price: float = Field(..., description="단가")
    name: str = Field(..., description="메뉴 이름")

    class Config:
        orm_mode = True

class OrderResponse(BaseModel):
    id: int = Field(..., description="주문 ID")
    user_id: int = Field(..., description="사용자 ID")
    total_price: float = Field(..., description="총 주문 금액")
    status: OrderStatus = Field(..., description="주문 상태")
    created_at: datetime = Field(..., description="주문 생성 시간")
    updated_at: datetime = Field(..., description="주문 업데이트 시간")
    address: str = Field(..., description="배달 주소")
    phone: str = Field(..., description="연락처")
    payment_status: str = Field(..., description="결제 상태")
    items: List[OrderItemResponse] = Field(..., description="주문 아이템 목록")

    class Config:
        orm_mode = True

class PaymentFailConfig(BaseModel):
    fail_percent: int = Field(..., description="결제 실패율(%)", example=30, ge=0, le=100)

# 데이터베이스 초기화
Base.metadata.create_all(bind=engine)

# FastAPI 애플리케이션 생성
app = FastAPI(
    title="Order Service API",
    description="""
    ## 음식 배달 마이크로서비스의 주문 관리 API
    
    이 API는 음식 배달 서비스의 주문 생성, 조회, 취소 기능을 제공합니다.
    
    주요 기능:
    * 새로운 주문 생성
    * 주문 상태 조회
    * 주문 취소
    * 결제 실패율 조정 (카오스 엔지니어링)
    
    특징:
    * 각 API는 마이크로서비스 아키텍처에 맞게 사용자 서비스와 레스토랑 서비스를 호출합니다
    * 주문 정보는 Redis에 5분간 캐싱됩니다
    * 결제 실패 시 자동 롤백 기능이 구현되어 있습니다
    * 취소가 불가능한 주문 상태가 관리됩니다
    
    **의존성 서비스:**
    * 사용자 서비스: JWT 토큰 검증 (/validate)
    * 레스토랑 서비스: 메뉴 정보 조회 및 재고 관리
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 미들웨어 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 의존성 주입
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 헬스체크 엔드포인트
@app.get(
    "/health", 
    tags=["상태 확인"], 
    summary="서비스 헬스체크",
    description="""
    서비스가 정상적으로 실행 중인지 확인합니다.
    
    이 엔드포인트는 로드 밸런서, 쿠버네티스 등의 상태 모니터링에 사용됩니다.
    서비스가 정상이면 healthy 상태를, 데이터베이스나 의존 서비스에 문제가 있으면 다른 상태를 반환합니다.
    """,
    response_description="서비스 상태 정보"
)
def health_check():
    """
    서비스 상태를 확인합니다.
    
    Returns:
        dict: 서비스 상태 정보 (healthy: 정상)
    """
    return {"status": "healthy"}

# 유저 서비스 호출
async def validate_user(token: str):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{USER_SERVICE_URL}/validate", headers=headers)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=401, detail=f"User validation failed: {str(e)}")

# 레스토랑 서비스 호출 - 메뉴 조회
async def get_menu(menu_id: int):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{RESTAURANT_SERVICE_URL}/menus/{menu_id}")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=404, detail=f"Menu not found: {str(e)}")

# 레스토랑 서비스 호출 - 재고 감소
async def update_inventory(menu_id: int, quantity: int):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{RESTAURANT_SERVICE_URL}/inventory/{menu_id}",
                json={"quantity": quantity}
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"Inventory update failed: {str(e)}")

# 레스토랑 서비스 호출 - 재고 복구 (취소 시)
async def restore_inventory(menu_id: int, quantity: int):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{RESTAURANT_SERVICE_URL}/inventory/{menu_id}/restore",
                json={"quantity": quantity}
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"Inventory restore failed: {str(e)}")

# 결제 처리 함수 (가상)
def process_payment(order_id: int, total_price: float) -> bool:
    # 설정된 확률로 결제 실패 시뮬레이션
    if random.randint(1, 100) <= payment_fail_percent:
        return False
    return True

# 인메모리 주문 정보 캐싱
def cache_order(order_id: int, order_data: Dict[str, Any]):
    """주문 정보를 Redis에 캐싱합니다"""
    cache_key = f"order:{order_id}"
    redis_client.setex(cache_key, 300, json.dumps(order_data, cls=DateTimeEncoder))

def get_cached_order(order_id: int) -> Optional[Dict[str, Any]]:
    cache_key = f"order:{order_id}"
    cached_order = redis_client.get(cache_key)
    if cached_order:
        return json.loads(cached_order)
    return None

# 주문 생성 엔드포인트
@app.post(
    "/orders", 
    response_model=OrderResponse,
    tags=["주문 관리"],
    summary="주문 생성",
    description="""
    새로운 주문을 생성합니다.
    
    **인증 필요:**
    * Authorization 헤더에 'Bearer {token}' 형식으로 JWT 토큰을 포함해야 합니다
    
    **요청 본문:**
    * items: 주문할 메뉴 목록 (메뉴 ID, 수량)
    * address: 배달 주소
    * phone: 연락처
    
    **프로세스:**
    1. JWT 토큰으로 사용자 인증 (User Service 호출)
    2. 메뉴 정보 확인 및 가격 계산 (Restaurant Service 호출)
    3. 재고 확인 및 감소 (Restaurant Service 호출)
    4. 결제 처리 
    5. 결제 실패 시 재고 자동 복구 (롤백)
    
    **결과 상태:**
    * 201 Created: 주문 생성 성공
    * 401 Unauthorized: 인증 실패
    * 400 Bad Request: 재고 부족 또는 결제 실패
    * 404 Not Found: 메뉴를 찾을 수 없음
    
    설정된 결제 실패율에 따라 일정 확률로 결제가 실패할 수 있습니다.
    결제 실패 시 주문은 'FAILED' 상태가 되고 재고가 자동 복구됩니다.
    """,
    status_code=status.HTTP_201_CREATED,
    response_description="생성된 주문 정보"
)
async def create_order(
    order: OrderCreate,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    새로운 주문을 생성합니다.
    
    **인증 필요**: 이 엔드포인트는 Bearer 토큰 인증이 필요합니다.
    
    **요청 정보**:
    - `restaurant_id`: 레스토랑 ID
    - `menu_items`: 주문할 메뉴 항목 리스트
        - `menu_id`: 메뉴 ID
        - `quantity`: 주문 수량
    
    **응답 정보**:
    - `order_id`: 생성된 주문의 고유 ID
    - `status`: 주문 상태
    - `total_price`: 총 주문 금액
    - `created_at`: 주문 생성 시간
    
    Args:
        order (OrderCreate): 주문 생성 정보 (아이템 목록, 주소, 연락처)
        token (str): OAuth2 인증 토큰
        db (Session): 데이터베이스 세션
        
    Raises:
        HTTPException: 
            - 401: 인증 실패
            - 404: 메뉴 찾을 수 없음
            - 400: 재고 부족 또는 결제 실패
        
    Returns:
        OrderResponse: 생성된 주문 정보
    
    의존성:
        - User Service: 사용자 인증
        - Restaurant Service: 메뉴 조회 및 재고 관리
    """
    # 사용자 유효성 검증
    user_data = await validate_user(token)
    user_id = user_data["user_id"]
    
    # 메뉴 정보와 총 가격 계산
    total_price = 0
    order_items_data = []
    
    for item in order.items:
        # 메뉴 정보 조회
        menu_data = await get_menu(item.menu_id)
        
        # 가격 계산
        item_price = menu_data["price"] * item.quantity
        total_price += item_price
        
        order_items_data.append({
            "menu_id": item.menu_id,
            "quantity": item.quantity,
            "price": menu_data["price"],
            "name": menu_data["name"]
        })
    
    # 주문 생성
    db_order = Order(
        user_id=user_id,
        total_price=total_price,
        address=order.address,
        phone=order.phone
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    
    # 주문 아이템 생성
    db_order_items = []
    for item_data in order_items_data:
        db_order_item = OrderItem(
            order_id=db_order.id,
            menu_id=item_data["menu_id"],
            quantity=item_data["quantity"],
            price=item_data["price"],
            name=item_data["name"]
        )
        db.add(db_order_item)
        db_order_items.append(db_order_item)
    
    db.commit()
    for item in db_order_items:
        db.refresh(item)
    
    # 재고 업데이트
    try:
        for item in order.items:
            await update_inventory(item.menu_id, item.quantity)
    except Exception as e:
        # 재고 업데이트 실패 시, 주문 취소
        db_order.status = OrderStatus.FAILED
        db.commit()
        raise HTTPException(status_code=400, detail=f"Inventory update failed: {str(e)}")
    
    # 결제 처리
    payment_success = process_payment(db_order.id, total_price)
    if payment_success:
        db_order.status = OrderStatus.CONFIRMED
        db_order.payment_status = "completed"
    else:
        db_order.status = OrderStatus.FAILED
        db_order.payment_status = "failed"
        
        # 결제 실패 시 재고 복구
        for item in order.items:
            try:
                await restore_inventory(item.menu_id, item.quantity)
            except Exception:
                # 재고 복구 실패는 로깅만 하고 계속 진행
                pass
    
    db.commit()
    
    # 응답 데이터 구성
    response_data = {
        "id": db_order.id,
        "user_id": db_order.user_id,
        "total_price": db_order.total_price,
        "status": db_order.status,
        "created_at": db_order.created_at,
        "updated_at": db_order.updated_at,
        "address": db_order.address,
        "phone": db_order.phone,
        "payment_status": db_order.payment_status,
        "items": [
            {
                "id": item.id,
                "menu_id": item.menu_id,
                "quantity": item.quantity,
                "price": item.price,
                "name": item.name
            } for item in db_order_items
        ]
    }
    
    # 주문 정보 캐싱
    cache_order(db_order.id, response_data)
    
    return response_data

# 주문 상태 조회 엔드포인트
@app.get(
    "/orders/{order_id}", 
    response_model=OrderResponse,
    tags=["주문 관리"],
    summary="주문 상태 조회",
    description="""
    주문 ID로 주문 상태 및 상세 정보를 조회합니다.
    
    **Path 파라미터:**
    * order_id: 조회할 주문의 고유 ID
    
    **캐싱 정책:**
    * Redis 캐싱이 적용되어 5분 동안 캐시됩니다
    * 캐시 키: "order:{order_id}"
    
    **응답:**
    * 주문의 상세 정보 (상태, 금액, 메뉴 목록 등)
    
    **오류 케이스:**
    * 주문이 존재하지 않는 경우 404 에러
    """,
    response_description="주문 상세 정보"
)
async def get_order(order_id: int, request: Request, db: Session = Depends(get_db)):
    """
    주문 ID로 주문 상태 및 상세 정보를 조회합니다.
    
    캐싱 정책:
        - 캐시 유효 시간: 5분
        - 캐시 키: "order:{order_id}"
    
    Args:
        order_id (int): 조회할 주문 ID
        request (Request): HTTP 요청 객체
        db (Session): 데이터베이스 세션
        
    Raises:
        HTTPException: 주문이 존재하지 않는 경우 404 에러
        
    Returns:
        OrderResponse: 주문 상세 정보
    """
    # 캐싱된 주문 정보 확인
    cached_order = get_cached_order(order_id)
    if cached_order:
        return cached_order
    
    # 캐싱된 정보가 없으면 DB에서 조회
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # 주문 아이템 조회
    order_items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    
    # 응답 데이터 구성
    response_data = {
        "id": order.id,
        "user_id": order.user_id,
        "total_price": order.total_price,
        "status": order.status,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        "address": order.address,
        "phone": order.phone,
        "payment_status": order.payment_status,
        "items": [
            {
                "id": item.id,
                "menu_id": item.menu_id,
                "quantity": item.quantity,
                "price": item.price,
                "name": item.name
            } for item in order_items
        ]
    }
    
    # 주문 정보 캐싱
    cache_order(order.id, response_data)
    
    return response_data

# 주문 취소 엔드포인트
@app.post(
    "/orders/{order_id}/cancel",
    tags=["주문 관리"],
    summary="주문 취소",
    description="""
    주문을 취소하고 재고를 복구합니다.
    
    **Path 파라미터:**
    * order_id: 취소할 주문의 고유 ID
    
    **프로세스:**
    1. 주문 존재 여부 및 취소 가능 상태 확인
    2. 주문 상태를 'CANCELLED'로 변경
    3. 레스토랑 서비스 호출하여 재고 복구
    4. 캐시 정보 삭제
    
    **취소 가능 조건:**
    * 주문이 이미 '배송 중' 또는 '배송 완료' 상태가 아니어야 함
    * 이미 취소된 주문은 다시 취소할 수 없음
    
    **오류 케이스:**
    * 주문이 존재하지 않는 경우: 404 에러
    * 이미 취소된 주문: 400 에러
    * 취소 불가능한 상태: 400 에러
    """,
    response_description="취소 결과"
)
async def cancel_order(order_id: int, request: Request, db: Session = Depends(get_db)):
    """
    주문을 취소하고 재고를 복구합니다.
    
    프로세스:
        1. 주문 존재 여부 및 취소 가능 상태 확인
        2. 주문 상태를 '취소됨'으로 변경
        3. 재고 복구 (Restaurant Service 호출)
        4. 캐시 정보 삭제
    
    제한사항:
        - 이미 취소된 주문은 다시 취소할 수 없음
        - 배송 중이거나 배송 완료된 주문은 취소할 수 없음
    
    Args:
        order_id (int): 취소할 주문 ID
        request (Request): HTTP 요청 객체
        db (Session): 데이터베이스 세션
        
    Raises:
        HTTPException: 
            - 404: 주문이 존재하지 않는 경우
            - 400: 이미 취소되었거나 취소 불가능한 상태인 경우
        
    Returns:
        dict: 취소 결과 메시지
        
    의존성:
        - Restaurant Service: 재고 복구
    """
    # 주문 조회
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # 이미 취소된 주문인지 확인
    if order.status == OrderStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Order is already cancelled")
    
    # 배송 중이거나 배송 완료된 주문은 취소 불가
    if order.status in [OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED]:
        raise HTTPException(status_code=400, detail="Cannot cancel order in current status")
    
    # 주문 아이템 조회
    order_items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    
    # 주문 상태 변경
    order.status = OrderStatus.CANCELLED
    db.commit()
    
    # 재고 복구
    for item in order_items:
        try:
            await restore_inventory(item.menu_id, item.quantity)
        except Exception as e:
            # 재고 복구 실패는 로깅만 하고 계속 진행
            pass
    
    # 캐시 삭제
    redis_client.delete(f"order:{order_id}")
    
    return {"message": "Order cancelled successfully", "order_id": order_id}

# 카오스 엔지니어링 - 결제 실패율 설정
@app.post(
    "/chaos/payment_fail",
    tags=["카오스 엔지니어링"],
    summary="결제 실패율 설정",
    description="""
    주문 생성 시 결제 실패 확률을 설정합니다.
    
    **요청 본문:**
    * fail_percent: 결제 실패율 (0~100%)
    
    설정된 확률에 따라 주문 생성 시 결제가 실패할 수 있습니다.
    결제 실패 시 주문은 'FAILED' 상태가 되고 재고가 자동 복구됩니다.
    
    이 기능은 시스템의 롤백 기능과 복원력을 테스트하는 데 유용합니다.
    
    예시 요청 본문:
    ```json
    {
      "fail_percent": 30
    }
    ```
    """,
    response_description="설정 결과"
)
def set_payment_fail_rate(config: PaymentFailConfig):
    """
    주문 결제 시 실패 확률을 설정합니다.
    
    Args:
        config (PaymentFailConfig): 결제 실패율 설정 (0-100%)
        
    Returns:
        dict: 설정 결과 메시지
        
    예시:
        ```json
        {
          "fail_percent": 30
        }
        ```
    """
    global payment_fail_percent
    payment_fail_percent = config.fail_percent
    return {"message": f"Payment failure rate set to {config.fail_percent}%"}

# 커스텀 OpenAPI 스키마 생성 함수 추가
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # 보안 스키마 추가
    openapi_schema["components"] = openapi_schema.get("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }
    
    # 기본 보안 요구사항 추가
    openapi_schema["security"] = [{"BearerAuth": []}]
    
    # 각 엔드포인트에 보안 요구사항 추가
    for path in openapi_schema["paths"]:
        for method in openapi_schema["paths"][path]:
            if method in ["get", "post", "put", "delete"]:
                operation = openapi_schema["paths"][path][method]
                
                # 주문 생성 엔드포인트에 보안 스키마 명시적으로 추가
                if path == "/orders" and method == "post":
                    operation["security"] = [{"BearerAuth": []}]
                
                # 설명과 요약 정보 개선
                if "summary" in operation and operation["summary"]:
                    # API 요약 정보를 강화하여 표시
                    operation["summary"] = f"👉 {operation['summary']}"
                
                # 툴팁에 표시될 설명 정보 강화
                if "description" in operation and operation["description"]:
                    # 요약 설명을 설명 시작 부분에 굵게 추가
                    first_line = operation["description"].split('\n')[0].strip()
                    enhanced_desc = f"**{first_line}**\n\n{operation['description']}"
                    operation["description"] = enhanced_desc
                
                # 태그에 아이콘 추가
                if "tags" in operation and operation["tags"]:
                    tags = operation["tags"]
                    for i, tag in enumerate(tags):
                        if tag == "주문 관리":
                            tags[i] = "🛒 주문 관리"
                        elif tag == "카오스 엔지니어링":
                            tags[i] = "⚡ 카오스 엔지니어링"
                        elif tag == "상태 확인":
                            tags[i] = "🔍 상태 확인"
                    operation["tags"] = tags
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True) 