import os
import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Form, status, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from opentelemetry import trace
from pydantic import BaseModel
from typing import Optional
import jwt
from datetime import datetime, timedelta
import hashlib

from shared.logger import ServiceLogger
from shared.middleware import LoggingMiddleware
from shared.telemetry import OpenTelemetryService
import socket
import platform
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

# JWT 설정
JWT_SECRET = os.environ.get("JWT_SECRET", "mysecretkey")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

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

# Pydantic 모델
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str

class Token(BaseModel):
    access_token: str
    token_type: str

# 보안 스키마
security = HTTPBearer()

# 사용자 데이터베이스 (실제로는 데이터베이스를 사용해야 함)
users_db = [
    {
        "id": 1, 
        "username": "testuser", 
        "email": "test@example.com",
        "password_hash": hashlib.sha256("testpass".encode()).hexdigest()
    }
]

def hash_password(password: str) -> str:
    """비밀번호 해시화"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, password_hash: str) -> bool:
    """비밀번호 검증"""
    return hashlib.sha256(password.encode()).hexdigest() == password_hash

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """JWT 토큰 생성"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def get_user_by_username(username: str):
    """사용자명으로 사용자 찾기"""
    return next((user for user in users_db if user["username"] == username), None)

def get_user_by_id(user_id: int):
    """사용자 ID로 사용자 찾기"""
    return next((user for user in users_db if user["id"] == user_id), None)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 가져오기 (JWT 토큰 검증)"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = get_user_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

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
        span.set_attribute("users.count", len(users_db))
        
        logger.info(f"사용자 목록 조회: {len(users_db)}명의 사용자가 있습니다.")
        return {"users": users_db}

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
                user = get_user_by_id(user_id)
                
                if user:
                    span.set_attribute("user.found", True)
                    span.set_attribute("user.name", user["username"])
                    
                    logger.info(f"사용자 ID {user_id} 조회 성공", user_data=user["username"])
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

@app.post("/signup", response_model=UserResponse)
async def signup(user_data: UserCreate):
    """회원가입 엔드포인트"""
    with telemetry.create_span("user_signup") as span:
        span.set_attribute("user.username", user_data.username)
        span.set_attribute("user.email", user_data.email)
        
        logger.info(f"회원가입 요청: {user_data.username}")
        
        # 사용자명 중복 확인
        if get_user_by_username(user_data.username):
            logger.warning(f"중복된 사용자명: {user_data.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered"
            )
        
        # 이메일 중복 확인
        existing_email = next((user for user in users_db if user["email"] == user_data.email), None)
        if existing_email:
            logger.warning(f"중복된 이메일: {user_data.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # 새 사용자 생성
        new_user_id = max([user["id"] for user in users_db], default=0) + 1
        new_user = {
            "id": new_user_id,
            "username": user_data.username,
            "email": user_data.email,
            "password_hash": hash_password(user_data.password)
        }
        
        users_db.append(new_user)
        
        logger.info(f"회원가입 성공: {user_data.username}")
        
        # 응답에서 password_hash 제외
        return UserResponse(
            id=new_user["id"],
            username=new_user["username"],
            email=new_user["email"]
        )

@app.post("/login", response_model=Token)
async def login(username: str = Form(...), password: str = Form(...)):
    """로그인 엔드포인트"""
    with telemetry.create_span("user_login") as span:
        span.set_attribute("user.username", username)
        
        logger.info(f"로그인 시도: {username}")
        
        # 사용자 찾기
        user = get_user_by_username(username)
        if not user:
            logger.warning(f"존재하지 않는 사용자: {username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password"
            )
        
        # 비밀번호 검증
        if not verify_password(password, user["password_hash"]):
            logger.warning(f"잘못된 비밀번호: {username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password"
            )
        
        # JWT 토큰 생성
        access_token = create_access_token(data={"sub": user["id"]})
        
        logger.info(f"로그인 성공: {username}")
        
        return Token(access_token=access_token, token_type="bearer")

@app.post("/validate", response_model=UserResponse)
async def validate_user(current_user: dict = Depends(get_current_user)):
    """사용자 토큰 검증 엔드포인트"""
    with telemetry.create_span("user_validate") as span:
        span.set_attribute("user.id", current_user["id"])
        span.set_attribute("user.username", current_user["username"])
        
        logger.info(f"토큰 검증 성공: {current_user['username']}")
        
        return UserResponse(
            id=current_user["id"],
            username=current_user["username"],
            email=current_user["email"]
        )

@app.get("/metrics")
async def metrics():
    """프로메테우스 메트릭 엔드포인트"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True) 