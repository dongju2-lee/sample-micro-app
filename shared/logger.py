import os
import logging
import json
from datetime import datetime
import traceback
import sys
from logging.handlers import RotatingFileHandler
import uuid

class ServiceLogger:
    """
    마이크로서비스를 위한 로깅 유틸리티 클래스
    
    로그를 구조화된 JSON 형식으로 출력하고 
    파일과 콘솔에 동시에 로그를 기록합니다.
    """
    
    def __init__(self, service_name, log_level=logging.INFO):
        self.service_name = service_name
        self.request_id = None
        
        # 로거 생성
        self.logger = logging.getLogger(service_name)
        self.logger.setLevel(log_level)
        self.logger.handlers = []  # 기존 핸들러 제거
        
        # 형식 정의
        formatter = logging.Formatter('%(message)s')
        
        # 콘솔 핸들러
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # 로그 디렉토리 생성
        base_log_dir = "/var/log/microservices"
        service_log_dir = f"{base_log_dir}/{service_name}"
        os.makedirs(service_log_dir, exist_ok=True)
        
        # 파일 핸들러
        file_handler = RotatingFileHandler(
            f"{service_log_dir}/service.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
    
    def set_request_id(self, request_id=None):
        """요청 ID 설정 (요청 추적용)"""
        self.request_id = request_id if request_id else str(uuid.uuid4())
        return self.request_id
    
    def _format_log(self, level, message, **kwargs):
        """로그 메시지를 구조화된 JSON으로 포맷팅"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": self.service_name,
            "level": level,
            "message": message
        }
        
        # 요청 ID가 있으면 추가
        if self.request_id:
            log_data["request_id"] = self.request_id
            
        # 추가 데이터
        for key, value in kwargs.items():
            log_data[key] = value
            
        return json.dumps(log_data)
    
    def info(self, message, **kwargs):
        """정보 레벨 로그"""
        self.logger.info(self._format_log("INFO", message, **kwargs))
    
    def warning(self, message, **kwargs):
        """경고 레벨 로그"""
        self.logger.warning(self._format_log("WARNING", message, **kwargs))
    
    def error(self, message, exc_info=None, **kwargs):
        """에러 레벨 로그"""
        error_info = {}
        
        # 예외 정보가 있으면 스택 트레이스 추가
        if exc_info:
            if isinstance(exc_info, BaseException):
                error_info["error_type"] = exc_info.__class__.__name__
                error_info["error_message"] = str(exc_info)
                error_info["traceback"] = traceback.format_exc()
            elif exc_info is True:
                error_info["traceback"] = traceback.format_exc()
        
        self.logger.error(self._format_log("ERROR", message, **{**error_info, **kwargs}))
    
    def debug(self, message, **kwargs):
        """디버그 레벨 로그"""
        self.logger.debug(self._format_log("DEBUG", message, **kwargs))
    
    def critical(self, message, exc_info=None, **kwargs):
        """심각한 오류 레벨 로그"""
        error_info = {}
        
        # 예외 정보가 있으면 스택 트레이스 추가
        if exc_info:
            if isinstance(exc_info, BaseException):
                error_info["error_type"] = exc_info.__class__.__name__
                error_info["error_message"] = str(exc_info)
                error_info["traceback"] = traceback.format_exc()
            elif exc_info is True:
                error_info["traceback"] = traceback.format_exc()
        
        self.logger.critical(self._format_log("CRITICAL", message, **{**error_info, **kwargs})) 