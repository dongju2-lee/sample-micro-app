import os
import time
import json
import random
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, select, update, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
import redis

# 로깅 관련 모듈 임포트
import sys
import logging
try:
    from shared.logger import ServiceLogger
    from shared.middleware import LoggingMiddleware
    LOGGING_ENABLED = True
except ImportError:
    print("Warning: Shared logging module not found. Logging disabled.")
    LOGGING_ENABLED = False

# 환경변수 설정
DB_URL = os.getenv("DB_URL", "postgresql://restaurant:pass@localhost:5432/restaurant")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/1")

# 데이터베이스 설정
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Redis 설정
redis_client = redis.from_url(REDIS_URL)

# 인위적 지연 및 에러 설정을 위한 전역 변수
global_delay_ms = 0
chaos_error_enabled = False

# 로거 초기화
logger = None
if LOGGING_ENABLED:
    logger = ServiceLogger("restaurant-service")

# 모델 정의
class Restaurant(Base):
    __tablename__ = "restaurants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    address = Column(String)
    phone = Column(String)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    menus = relationship("Menu", back_populates="restaurant")

class Menu(Base):
    __tablename__ = "menus"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    name = Column(String, index=True)
    description = Column(Text)
    price = Column(Float)
    image_url = Column(String)
    is_available = Column(Boolean, default=True)
    inventory = Column(Integer, default=100)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    restaurant = relationship("Restaurant", back_populates="menus")

# Pydantic 모델
class RestaurantBase(BaseModel):
    name: str = Field(..., description="음식점 이름", example="맛있는 치킨")
    address: str = Field(..., description="음식점 주소", example="서울시 강남구 123-45")
    phone: str = Field(..., description="음식점 전화번호", example="02-1234-5678")
    description: Optional[str] = Field(None, description="음식점 설명", example="최고의 치킨 전문점")

class RestaurantCreate(RestaurantBase):
    pass

class RestaurantResponse(RestaurantBase):
    id: int = Field(..., description="음식점 고유 ID")
    created_at: datetime = Field(..., description="등록 시간")

    class Config:
        orm_mode = True

class MenuBase(BaseModel):
    name: str = Field(..., description="메뉴 이름", example="후라이드 치킨")
    description: Optional[str] = Field(None, description="메뉴 설명", example="바삭바삭한 후라이드 치킨")
    price: float = Field(..., description="메뉴 가격", example=18000)
    image_url: Optional[str] = Field(None, description="메뉴 이미지 URL", example="https://example.com/fried_chicken.jpg")
    inventory: int = Field(100, description="재고 수량", example=100)

class MenuCreate(MenuBase):
    restaurant_id: int = Field(..., description="음식점 ID", example=1)

class MenuResponse(MenuBase):
    id: int = Field(..., description="메뉴 고유 ID")
    restaurant_id: int = Field(..., description="메뉴가 속한 음식점 ID")
    is_available: bool = Field(..., description="메뉴 이용 가능 여부")
    created_at: datetime = Field(..., description="메뉴 등록 시간")

    class Config:
        orm_mode = True

class InventoryUpdate(BaseModel):
    quantity: int = Field(..., description="수량 변경 값", example=1, gt=0)

class InventoryDelayConfig(BaseModel):
    delay_ms: int = Field(..., description="지연 시간(밀리초)", example=3000, gt=0)

# 데이터베이스 초기화
Base.metadata.create_all(bind=engine)

# FastAPI 애플리케이션 생성
app = FastAPI(
    title="Restaurant Service API",
    description="""
    ## 음식 배달 마이크로서비스의 음식점, 메뉴 관리 및 재고 관리 API
    
    이 API는 음식점 정보, 메뉴 관리, 재고 관리 기능을 제공합니다.
    
    주요 기능:
    * 음식점 및 메뉴 정보 조회
    * 동시성이 제어된 재고 관리
    * Redis 기반 메뉴 정보 캐싱
    * 카오스 엔지니어링 (재고 업데이트 지연) 기능
    
    특징:
    * 모든 메뉴 정보는 10초간 캐싱됩니다
    * 단일 메뉴 정보는 30초간 캐싱됩니다
    * 동시성 제어를 위해 비관적 락(Pessimistic Lock)이 사용됩니다
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

# 로깅 미들웨어 추가
if LOGGING_ENABLED and logger:
    app.add_middleware(LoggingMiddleware, logger=logger)
    logger.info("Restaurant Service 시작됨", version="1.0.0")

# 의존성 주입
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 샘플 데이터 추가 함수
def insert_sample_data(db: Session):
    # 레스토랑이 없는 경우에만 샘플 데이터 추가
    if db.query(Restaurant).count() == 0:
        # 레스토랑 추가
        restaurants = [
            {
                "name": "맛있는 치킨",
                "address": "서울시 강남구 123-45",
                "phone": "02-1234-5678",
                "description": "최고의 치킨 전문점"
            },
            {
                "name": "행복한 피자",
                "address": "서울시 서초구 456-78",
                "phone": "02-5678-1234",
                "description": "신선한 재료로 만든 피자"
            },
            {
                "name": "신선한 샐러드",
                "address": "서울시 송파구 789-12",
                "phone": "02-9876-5432",
                "description": "건강한 식사를 위한 샐러드"
            }
        ]
        
        for restaurant_data in restaurants:
            restaurant = Restaurant(**restaurant_data)
            db.add(restaurant)
        
        db.commit()
        
        # 메뉴 추가
        restaurant1 = db.query(Restaurant).filter(Restaurant.name == "맛있는 치킨").first()
        restaurant2 = db.query(Restaurant).filter(Restaurant.name == "행복한 피자").first()
        restaurant3 = db.query(Restaurant).filter(Restaurant.name == "신선한 샐러드").first()
        
        menus = [
            {
                "restaurant_id": restaurant1.id,
                "name": "후라이드 치킨",
                "description": "바삭바삭한 후라이드 치킨",
                "price": 18000,
                "image_url": "https://example.com/fried_chicken.jpg",
                "inventory": 100
            },
            {
                "restaurant_id": restaurant1.id,
                "name": "양념 치킨",
                "description": "달콤매콤한 양념 치킨",
                "price": 19000,
                "image_url": "https://example.com/spicy_chicken.jpg",
                "inventory": 100
            },
            {
                "restaurant_id": restaurant2.id,
                "name": "페퍼로니 피자",
                "description": "클래식한 페퍼로니 피자",
                "price": 20000,
                "image_url": "https://example.com/pepperoni_pizza.jpg",
                "inventory": 50
            },
            {
                "restaurant_id": restaurant2.id,
                "name": "불고기 피자",
                "description": "한국적인 맛의 불고기 피자",
                "price": 22000,
                "image_url": "https://example.com/bulgogi_pizza.jpg",
                "inventory": 50
            },
            {
                "restaurant_id": restaurant3.id,
                "name": "시저 샐러드",
                "description": "신선한 야채와 특제 시저 드레싱",
                "price": 12000,
                "image_url": "https://example.com/caesar_salad.jpg",
                "inventory": 80
            },
            {
                "restaurant_id": restaurant3.id,
                "name": "그릭 샐러드",
                "description": "페타 치즈와 올리브 오일의 조화",
                "price": 13000,
                "image_url": "https://example.com/greek_salad.jpg",
                "inventory": 80
            }
        ]
        
        for menu_data in menus:
            menu = Menu(**menu_data)
            db.add(menu)
        
        db.commit()

# 미들웨어 추가
@app.middleware("http")
async def add_inventory_delay_middleware(request: Request, call_next):
    # 특정 API에 지연 적용 (재고 관련)
    if request.url.path.startswith("/inventory") and global_delay_ms > 0:
        time.sleep(global_delay_ms / 1000)
    
    response = await call_next(request)
    return response

# 헬스체크 엔드포인트
@app.get(
    "/health", 
    tags=["상태 확인"], 
    summary="서비스 헬스체크",
    description="""
    서비스가 정상적으로 실행 중인지 확인합니다.
    
    이 엔드포인트는 로드 밸런서, 쿠버네티스 등의 상태 모니터링에 사용됩니다.
    서비스가 정상이면 healthy 상태를 반환합니다.
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

# 초기 데이터 추가
@app.on_event("startup")
async def startup_event():
    db = SessionLocal()
    insert_sample_data(db)
    db.close()

# 전체 메뉴 조회 (캐싱 적용)
@app.get(
    "/menus", 
    response_model=List[MenuResponse],
    tags=["메뉴 관리"],
    summary="전체 메뉴 목록 조회",
    description="""
    시스템에 등록된 모든 메뉴 정보를 조회합니다.
    
    **캐싱 정책:**
    * Redis 캐싱이 적용되어 10초 동안 캐시됩니다
    * 캐시 키: "all_menus"
    * 재고 업데이트 시 캐시가 자동으로 무효화됩니다
    
    이 API는 사용자에게 전체 메뉴 목록을 보여주는 데 사용됩니다.
    """,
    response_description="메뉴 목록"
)
def get_all_menus(db: Session = Depends(get_db)):
    """
    모든 메뉴 정보를 조회합니다. Redis 캐싱이 적용되어 있습니다.
    
    캐싱 정책:
        - 캐시 유효 시간: 10초
        - 캐시 키: "all_menus"
    
    Args:
        db (Session): 데이터베이스 세션
        
    Returns:
        List[Menu]: 메뉴 목록
    """
    # Redis에서 캐시된 결과 확인
    cached_menus = redis_client.get("all_menus")
    if cached_menus:
        return json.loads(cached_menus)
    
    # 캐시가 없으면 DB에서 조회
    menus = db.query(Menu).all()
    
    # 결과를 JSON으로 변환
    menu_list = [
        {
            "id": menu.id,
            "restaurant_id": menu.restaurant_id,
            "name": menu.name,
            "description": menu.description,
            "price": menu.price,
            "image_url": menu.image_url,
            "inventory": menu.inventory,
            "is_available": menu.is_available,
            "created_at": menu.created_at.isoformat()
        }
        for menu in menus
    ]
    
    # Redis에 캐싱 (10초 유효)
    redis_client.setex("all_menus", 10, json.dumps(menu_list))
    
    return menu_list

# 단일 메뉴 상세 조회 (캐싱 적용)
@app.get(
    "/menus/{menu_id}", 
    response_model=MenuResponse,
    tags=["메뉴 관리"],
    summary="단일 메뉴 상세 조회",
    description="""
    특정 메뉴의 상세 정보를 조회합니다.
    
    **Path 파라미터:**
    * menu_id: 조회할 메뉴의 고유 ID
    
    **캐싱 정책:**
    * Redis 캐싱이 적용되어 30초 동안 캐시됩니다
    * 캐시 키: "menu:{menu_id}"
    * 재고 업데이트 시 캐시가 자동으로 무효화됩니다
    
    메뉴가 존재하지 않는 경우 404 오류가 발생합니다.
    """,
    response_description="메뉴 상세 정보"
)
def get_menu(menu_id: int, db: Session = Depends(get_db)):
    """
    특정 ID의 메뉴 상세 정보를 조회합니다. Redis 캐싱이 적용되어 있습니다.
    
    캐싱 정책:
        - 캐시 유효 시간: 30초
        - 캐시 키: "menu:{menu_id}"
    
    Args:
        menu_id (int): 조회할 메뉴 ID
        db (Session): 데이터베이스 세션
        
    Raises:
        HTTPException: 메뉴가 존재하지 않는 경우 404 에러
        
    Returns:
        Menu: 메뉴 상세 정보
    """
    # Redis에서 캐시된 결과 확인
    cache_key = f"menu:{menu_id}"
    cached_menu = redis_client.get(cache_key)
    if cached_menu:
        return json.loads(cached_menu)
    
    # 캐시가 없으면 DB에서 조회
    menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    
    # 결과를 JSON으로 변환
    menu_data = {
        "id": menu.id,
        "restaurant_id": menu.restaurant_id,
        "name": menu.name,
        "description": menu.description,
        "price": menu.price,
        "image_url": menu.image_url,
        "inventory": menu.inventory,
        "is_available": menu.is_available,
        "created_at": menu.created_at.isoformat()
    }
    
    # Redis에 캐싱 (30초 유효)
    redis_client.setex(cache_key, 30, json.dumps(menu_data))
    
    return menu_data

# 재고 감소 (동시성 제어 적용)
@app.put(
    "/inventory/{menu_id}",
    tags=["재고 관리"],
    summary="메뉴 재고 감소",
    description="""
    특정 메뉴의 재고를 감소시킵니다.
    
    **Path 파라미터:**
    * menu_id: 재고를 감소시킬 메뉴의 고유 ID
    
    **요청 본문:**
    * quantity: 감소시킬 수량 (1 이상의 정수)
    
    **동시성 제어:**
    * 비관적 락(Pessimistic Lock)을 사용하여 동시성 문제 방지
    * SELECT ... FOR UPDATE 쿼리로 트랜잭션 중 레코드 잠금
    
    **응답:**
    * 업데이트 후 남은 재고 수량
    * 재고가 0이 되면 메뉴는 자동으로 비활성화됩니다
    
    **오류 케이스:**
    * 메뉴가 없는 경우 404 에러
    * 재고가 부족한 경우 400 에러
    
    재고 업데이트 성공 시 관련 캐시가 자동으로 삭제됩니다.
    """,
    response_description="업데이트된 재고 정보"
)
def update_inventory(menu_id: int, update: InventoryUpdate, db: Session = Depends(get_db)):
    """
    메뉴 재고를 감소시킵니다. 동시성 제어가 적용되어 있습니다.
    
    동시성 제어:
        - 비관적 락(Pessimistic Lock) 사용
        - SELECT ... FOR UPDATE 쿼리로 레코드 잠금
    
    Args:
        menu_id (int): 재고를 감소시킬 메뉴 ID
        update (InventoryUpdate): 감소시킬 수량 정보
        db (Session): 데이터베이스 세션
        
    Raises:
        HTTPException: 메뉴가 존재하지 않거나 재고가 부족한 경우
        
    Returns:
        dict: 업데이트된 재고 정보
    """
    # 비관적 락 적용 (FOR UPDATE)
    stmt = select(Menu).where(Menu.id == menu_id).with_for_update()
    result = db.execute(stmt)
    menu = result.scalar_one_or_none()
    
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    
    # 재고 부족 체크
    if menu.inventory < update.quantity:
        raise HTTPException(status_code=400, detail="Not enough inventory")
    
    # 재고 감소
    menu.inventory -= update.quantity
    
    # 재고가 0이면 메뉴 비활성화
    if menu.inventory <= 0:
        menu.is_available = False
    
    db.commit()
    
    # Redis 캐시 삭제
    redis_client.delete(f"menu:{menu_id}")
    redis_client.delete("all_menus")
    
    return {"menu_id": menu_id, "remaining_inventory": menu.inventory}

# 재고 증가 (주문 취소 시 호출)
@app.put(
    "/inventory/{menu_id}/restore",
    tags=["재고 관리"],
    summary="메뉴 재고 복구",
    description="""
    주문 취소 시 메뉴 재고를 복구합니다.
    
    **Path 파라미터:**
    * menu_id: 재고를 복구할 메뉴의 고유 ID
    
    **요청 본문:**
    * quantity: 복구할 수량 (1 이상의 정수)
    
    **동시성 제어:**
    * 비관적 락(Pessimistic Lock)을 사용하여 동시성 문제 방지
    * SELECT ... FOR UPDATE 쿼리로 트랜잭션 중 레코드 잠금
    
    **응답:**
    * 업데이트 후 남은 재고 수량
    * 비활성화된 메뉴는 재고가 복구되면 자동으로 활성화됩니다
    
    주문 서비스의 주문 취소 API에서 내부적으로 호출됩니다.
    재고 복구 성공 시 관련 캐시가 자동으로 삭제됩니다.
    """,
    response_description="복구된 재고 정보"
)
def restore_inventory(menu_id: int, update: InventoryUpdate, db: Session = Depends(get_db)):
    """
    주문 취소 시 메뉴 재고를 복구합니다. 동시성 제어가 적용되어 있습니다.
    
    동시성 제어:
        - 비관적 락(Pessimistic Lock) 사용
        - SELECT ... FOR UPDATE 쿼리로 레코드 잠금
    
    Args:
        menu_id (int): 재고를 복구할 메뉴 ID
        update (InventoryUpdate): 복구할 수량 정보
        db (Session): 데이터베이스 세션
        
    Raises:
        HTTPException: 메뉴가 존재하지 않는 경우
        
    Returns:
        dict: 업데이트된 재고 정보
    """
    # 비관적 락 적용 (FOR UPDATE)
    stmt = select(Menu).where(Menu.id == menu_id).with_for_update()
    result = db.execute(stmt)
    menu = result.scalar_one_or_none()
    
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    
    # 재고 증가
    menu.inventory += update.quantity
    
    # 메뉴가 비활성화 상태였다면 활성화
    if not menu.is_available and menu.inventory > 0:
        menu.is_available = True
    
    db.commit()
    
    # Redis 캐시 삭제
    redis_client.delete(f"menu:{menu_id}")
    redis_client.delete("all_menus")
    
    return {"menu_id": menu_id, "remaining_inventory": menu.inventory}

# 레스토랑 목록 조회
@app.get(
    "/restaurants", 
    response_model=List[RestaurantResponse],
    tags=["음식점 관리"],
    summary="음식점 목록 조회",
    description="""
    시스템에 등록된 모든 음식점 정보를 조회합니다.
    
    음식점 목록을 페이지네이션 없이 전체 조회합니다.
    이 API는 사용자에게 음식점 선택 옵션을 제공하는 데 사용됩니다.
    """,
    response_description="음식점 목록"
)
def get_all_restaurants(db: Session = Depends(get_db)):
    """
    모든 음식점 정보를 조회합니다.
    
    Args:
        db (Session): 데이터베이스 세션
        
    Returns:
        List[Restaurant]: 음식점 목록
    """
    restaurants = db.query(Restaurant).all()
    return restaurants

# 카오스 엔지니어링 - 재고 업데이트 지연 설정
@app.post(
    "/chaos/inventory_delay",
    tags=["카오스 엔지니어링"],
    summary="재고 업데이트 지연 설정",
    description="""
    재고 관련 API에 인위적인 지연을 추가합니다.
    
    **요청 본문:**
    * delay_ms: 지연 시간(밀리초, 1000ms = 1초)
    
    설정 후 /inventory로 시작하는 모든 API 엔드포인트에 
    지정된 시간만큼의 지연이 발생합니다.
    
    성능 테스트, 타임아웃 테스트, 장애 대응 테스트에 유용합니다.
    
    예시 요청 본문:
    ```json
    {
      "delay_ms": 3000
    }
    ```
    """,
    response_description="지연 설정 결과"
)
def set_inventory_delay(config: InventoryDelayConfig):
    """
    재고 업데이트 API에 인위적인 지연을 설정합니다.
    
    Args:
        config (InventoryDelayConfig): 지연 시간(밀리초) 설정
        
    Returns:
        dict: 설정된 지연 시간 메시지
        
    예시:
        ```json
        {
          "delay_ms": 3000
        }
        ```
    """
    global global_delay_ms
    global_delay_ms = config.delay_ms
    return {"message": f"Inventory update delay set to {config.delay_ms}ms"}

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
    
    # API 상세 정보 추가
    for path in openapi_schema["paths"]:
        for method in openapi_schema["paths"][path]:
            if method in ["get", "post", "put", "delete"]:
                operation = openapi_schema["paths"][path][method]
                
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
                        if tag == "메뉴 관리":
                            tags[i] = "🍔 메뉴 관리"
                        elif tag == "재고 관리":
                            tags[i] = "📦 재고 관리"
                        elif tag == "음식점 관리":
                            tags[i] = "🏪 음식점 관리"
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