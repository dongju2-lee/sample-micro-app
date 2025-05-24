import time
import random
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from fastapi import FastAPI, HTTPException, Depends, status, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import redis

# 로깅 관련 모듈 임포트
import sys
import logging
try:
    from shared.logger import ServiceLogger
    from shared.middleware import LoggingMiddleware
    from shared.prometheus_middleware import PrometheusMiddleware, get_metrics_endpoint
    LOGGING_ENABLED = True
    PROMETHEUS_ENABLED = True
except ImportError:
    print("Warning: Shared logging module not found. Logging disabled.")
    LOGGING_ENABLED = False
    PROMETHEUS_ENABLED = False

# 환경변수 설정
DB_URL = os.getenv("DB_URL", "postgresql://user:pass@localhost:5432/user")
JWT_SECRET = os.getenv("JWT_SECRET", "mysecretkey")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# 데이터베이스 설정
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Redis 설정
redis_client = redis.from_url(REDIS_URL)

# 인위적 지연 및 에러 설정을 위한 전역 변수
global_delay_ms = 0
chaos_error_enabled = False

# 유저 모델
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# Pydantic 모델
class UserBase(BaseModel):
    username: str = Field(..., description="사용자 아이디", example="user123")
    email: str = Field(..., description="사용자 이메일", example="user@example.com")

class UserCreate(UserBase):
    password: str = Field(..., description="사용자 비밀번호", example="password123")

class UserResponse(UserBase):
    id: int = Field(..., description="사용자 고유 ID")
    is_active: bool = Field(..., description="계정 활성화 상태")
    created_at: datetime = Field(..., description="계정 생성 시간")

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str = Field(..., description="JWT 액세스 토큰")
    token_type: str = Field(..., description="토큰 타입", example="bearer")

class TokenData(BaseModel):
    username: Optional[str] = Field(None, description="사용자 아이디")

class ChaosDelayConfig(BaseModel):
    delay_ms: int = Field(..., description="지연 시간(밀리초)", example=1500)

class ChaosErrorConfig(BaseModel):
    enable: bool = Field(..., description="에러 발생 활성화 여부", example=True)

# 패스워드 컨텍스트 및 OAuth2 설정
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# 데이터베이스 초기화
Base.metadata.create_all(bind=engine)

# 로거 초기화
logger = None
if LOGGING_ENABLED:
    logger = ServiceLogger("user-service")

# FastAPI 애플리케이션 생성
app = FastAPI(
    title="User Service API",
    description="""
    ## 음식 배달 마이크로서비스의 사용자 인증 및 관리 API

    이 API는 사용자 계정 관리, 인증, 토큰 발급 기능을 제공합니다.
    
    주요 기능:
    * 회원 가입 및 로그인
    * JWT 토큰 기반 인증
    * 사용자 정보 조회
    * 카오스 엔지니어링 (장애 주입) 기능
    
    사용자 인증 과정:
    1. /signup 엔드포인트로 회원 가입
    2. /login 엔드포인트로 JWT 토큰 발급
    3. 발급받은 토큰을 Authorization 헤더에 Bearer 형식으로 포함
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
    logger.info("User Service 시작됨", version="1.0.0")

# Prometheus 미들웨어 추가
if PROMETHEUS_ENABLED:
    app.add_middleware(PrometheusMiddleware, service_name="user-service")

# 의존성 주입
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 미들웨어 추가
@app.middleware("http")
async def add_chaos_middleware(request: Request, call_next):
    # 인위적 지연 적용
    if global_delay_ms > 0:
        time.sleep(global_delay_ms / 1000)
    
    # URL 파라미터 지연 적용
    delay_param = request.query_params.get("delay")
    if delay_param and delay_param.isdigit():
        time.sleep(int(delay_param) / 1000)
    
    # 인위적 에러 발생
    if chaos_error_enabled and random.random() < 0.5:
        return Response(
            status_code=500,
            content="{'error': 'Chaos engineering induced error'}",
            media_type="application/json"
        )
    
    response = await call_next(request)
    return response

# 유틸리티 함수
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def authenticate_user(db: Session, username: str, password: str):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == token_data.username).first()
    if user is None:
        raise credentials_exception
    return user

# 헬스체크 엔드포인트
# Prometheus 메트릭 엔드포인트
if PROMETHEUS_ENABLED:
    @app.get(
        "/metrics",
        tags=["모니터링"],
        summary="Prometheus 메트릭",
        description="Prometheus가 수집할 수 있는 메트릭 데이터를 반환합니다.",
        response_description="Prometheus 형식의 메트릭 데이터"
    )
    async def metrics():
        return await get_metrics_endpoint()()

@app.get(
    "/health", 
    tags=["상태 확인"], 
    summary="서비스 헬스체크",
    description="서비스가 정상적으로 실행 중인지 확인합니다. 서비스 상태 모니터링에 사용됩니다.",
    response_description="서비스 상태 정보"
)
def health_check():
    """
    서비스 상태를 확인합니다.
    
    Returns:
        dict: 서비스 상태 정보 (healthy: 정상)
    """
    return {"status": "healthy"}

# 회원가입 엔드포인트
@app.post(
    "/signup", 
    response_model=UserResponse,
    tags=["인증"],
    summary="회원 가입",
    description="""
    신규 사용자를 등록합니다. 
    
    필수 정보:
    - username: 사용자 아이디 (중복 불가)
    - email: 이메일 주소 (중복 불가)
    - password: 비밀번호
    
    중복된 아이디나 이메일이 있는 경우 400 오류가 발생합니다.
    """,
    status_code=status.HTTP_201_CREATED,
    response_description="생성된 사용자 정보"
)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    """
    신규 사용자를 등록합니다.
    
    Args:
        user (UserCreate): 사용자 등록 정보 (아이디, 이메일, 비밀번호)
        
    Raises:
        HTTPException: 중복된 아이디나 이메일이 존재하는 경우
        
    Returns:
        User: 생성된 사용자 정보 (비밀번호 제외)
    """
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    db_email = db.query(User).filter(User.email == user.email).first()
    if db_email:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    db_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# 로그인 엔드포인트
@app.post(
    "/login", 
    response_model=Token,
    tags=["인증"],
    summary="로그인",
    description="""
    사용자 인증 후 JWT 토큰을 발급합니다.
    
    로그인 방법:
    - username과 password를 form data로 전송 (OAuth2 형식)
    - 인증 성공 시 액세스 토큰 발급
    - 발급된 토큰은 60분간 유효
    
    이후 API 호출 시 Authorization 헤더에 'Bearer {token}' 형식으로 토큰을 포함해야 합니다.
    """,
    response_description="발급된 JWT 토큰"
)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    사용자 인증 및 JWT 토큰 발급.
    
    Args:
        form_data (OAuth2PasswordRequestForm): 로그인 폼 데이터 (아이디, 비밀번호)
        
    Raises:
        HTTPException: 인증 실패 시 401 에러 발생
        
    Returns:
        Token: JWT 액세스 토큰
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# 유저 정보 조회 엔드포인트
@app.get(
    "/users/{user_id}", 
    response_model=UserResponse,
    tags=["사용자 관리"],
    summary="사용자 정보 조회",
    description="""
    지정된 ID의 사용자 정보를 조회합니다.
    
    Path 파라미터:
    - user_id: 조회할 사용자의 고유 ID
    
    사용자가 존재하지 않는 경우 404 오류가 발생합니다.
    """,
    response_description="사용자 상세 정보"
)
def read_user(user_id: int, db: Session = Depends(get_db)):
    """
    지정된 ID의 사용자 정보를 조회합니다.
    
    Args:
        user_id (int): 조회할 사용자 ID
        
    Raises:
        HTTPException: 사용자가 존재하지 않는 경우 404 에러
        
    Returns:
        User: 사용자 정보
    """
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user

# 사용자 유효성 검증 엔드포인트 (주문 시 사용)
@app.post(
    "/validate",
    tags=["사용자 관리"],
    summary="사용자 유효성 검증",
    description="""
    토큰으로 사용자를 인증하고 유효성을 검증합니다.
    
    주문 서비스에서 내부적으로 호출하는 API입니다.
    Authorization 헤더에 'Bearer {token}' 형식으로 토큰을 포함해야 합니다.
    
    카오스 엔지니어링 기능:
    - ?delay=2000 파라미터를 사용해 인위적 지연 발생 가능 (밀리초 단위)
    - 예: /validate?delay=2000 (2초 지연)
    """,
    response_description="유효한 사용자 정보"
)
def validate_user(current_user: User = Depends(get_current_user)):
    """
    JWT 토큰을 통해 사용자 유효성을 검증합니다.
    
    Args:
        current_user (User): 인증된 현재 사용자 (토큰에서 추출)
        
    Returns:
        dict: 사용자 유효성 및 기본 정보
    
    참고:
        - 이 API에는 ?delay=2000 파라미터를 사용해 인위적 지연을 발생시킬 수 있습니다.
        - 예: /validate?delay=2000 (2초 지연)
    """
    return {"valid": True, "user_id": current_user.id, "username": current_user.username}

# 카오스 엔지니어링 - 지연 설정
@app.post(
    "/chaos/delay",
    tags=["카오스 엔지니어링"],
    summary="인위적 지연 설정",
    description="""
    모든 API 호출에 인위적인 지연을 추가합니다.
    
    지연 시간을 밀리초(ms) 단위로 설정합니다.
    설정 후 모든 API 호출에 지정된 시간만큼의 지연이 발생합니다.
    성능 테스트 및 장애 대응 테스트에 유용합니다.
    
    예시 요청 본문:
    ```json
    {
      "delay_ms": 1500
    }
    ```
    """,
    response_description="지연 설정 결과"
)
def set_chaos_delay(config: ChaosDelayConfig):
    """
    모든 API 요청에 인위적인 지연을 설정합니다.
    
    Args:
        config (ChaosDelayConfig): 지연 시간(밀리초) 설정
        
    Returns:
        dict: 설정된 지연 시간 메시지
    
    예시:
        ```json
        {
          "delay_ms": 1500
        }
        ```
    """
    global global_delay_ms
    global_delay_ms = config.delay_ms
    return {"message": f"Delay set to {config.delay_ms}ms"}

# 카오스 엔지니어링 - 에러 발생 설정
@app.post(
    "/chaos/error",
    tags=["카오스 엔지니어링"],
    summary="인위적 에러 발생 설정",
    description="""
    모든 API 호출에 50% 확률로 500 에러가 발생하도록 설정합니다.
    
    활성화 시 모든 API 호출에 50% 확률로 500 Internal Server Error가 발생합니다.
    시스템의 장애 복구 메커니즘과 회복력을 테스트하는 데 유용합니다.
    
    예시 요청 본문:
    ```json
    {
      "enable": true
    }
    ```
    """,
    response_description="에러 설정 결과"
)
def set_chaos_error(config: ChaosErrorConfig):
    """
    50% 확률로 API 호출에 500 에러가 발생하도록 설정합니다.
    
    Args:
        config (ChaosErrorConfig): 에러 발생 활성화 여부
        
    Returns:
        dict: 에러 발생 설정 메시지
    
    예시:
        ```json
        {
          "enable": true
        }
        ```
    """
    global chaos_error_enabled
    chaos_error_enabled = config.enable
    return {"message": f"Error injection set to: {config.enable}"}

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
                        if tag == "인증":
                            tags[i] = "🔐 인증"
                        elif tag == "사용자 관리":
                            tags[i] = "👤 사용자 관리"
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