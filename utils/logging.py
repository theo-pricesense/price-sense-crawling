"""
Logging configuration and utilities for Price Sense crawler system.
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from config.settings import settings


class JsonFormatter(logging.Formatter):
    """JSON 형태로 로그를 포맷하는 커스텀 포맷터"""
    
    def format(self, record: logging.LogRecord) -> str:
        """로그 레코드를 JSON 형태로 변환"""
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process_id": record.process,
            "thread_id": record.thread,
        }
        
        # 예외 정보가 있는 경우 추가
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # 추가 필드가 있는 경우 포함
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)
        
        # 트레이스 정보 포함 (설정에 따라)
        if settings.logging.include_trace and hasattr(record, "trace_id"):
            log_entry["trace_id"] = record.trace_id
        
        return json.dumps(log_entry, ensure_ascii=False)


class CrawlerLogger:
    """크롤러 전용 로거 설정 및 관리"""
    
    def __init__(self):
        self._loggers: Dict[str, logging.Logger] = {}
        self._setup_root_logger()
    
    def _setup_root_logger(self) -> None:
        """루트 로거 설정"""
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, settings.logging.level.upper()))
        
        # 기존 핸들러 제거
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # 콘솔 핸들러 추가
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        
        if settings.logging.json_logging:
            console_handler.setFormatter(JsonFormatter())
        else:
            console_handler.setFormatter(logging.Formatter(settings.logging.format))
        
        root_logger.addHandler(console_handler)
        
        # 파일 핸들러 추가 (설정된 경우)
        if settings.logging.file_path:
            self._add_file_handler(root_logger)
    
    def _add_file_handler(self, logger: logging.Logger) -> None:
        """파일 핸들러 추가"""
        log_file = Path(settings.logging.file_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 로테이션 파일 핸들러
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=settings.logging.max_file_size,
            backupCount=settings.logging.backup_count,
            encoding='utf-8'
        )
        
        file_handler.setLevel(logging.DEBUG)
        
        if settings.logging.json_logging:
            file_handler.setFormatter(JsonFormatter())
        else:
            file_handler.setFormatter(logging.Formatter(settings.logging.format))
        
        logger.addHandler(file_handler)
    
    def get_logger(self, name: str) -> logging.Logger:
        """특정 이름의 로거 반환"""
        if name not in self._loggers:
            self._loggers[name] = logging.getLogger(name)
        
        return self._loggers[name]
    
    def log_crawl_start(self, logger: logging.Logger, task_data: Dict[str, Any]) -> None:
        """크롤링 시작 로그"""
        extra_fields = {
            "event_type": "crawl_start",
            "task_id": task_data.get("task_id"),
            "product_id": task_data.get("product_id"),
            "platform": task_data.get("platform"),
            "url": task_data.get("url"),
            "priority": task_data.get("priority", "normal")
        }
        
        # LogRecord에 extra_fields 추가
        record = logger.makeRecord(
            logger.name, logging.INFO, __file__, 0,
            f"Started crawling task: {task_data.get('task_id', 'unknown')}",
            (), None
        )
        record.extra_fields = extra_fields
        logger.handle(record)
    
    def log_crawl_success(self, logger: logging.Logger, task_id: str, 
                         scraped_data: Dict[str, Any], execution_time: float) -> None:
        """크롤링 성공 로그"""
        extra_fields = {
            "event_type": "crawl_success",
            "task_id": task_id,
            "execution_time": execution_time,
            "confidence_score": scraped_data.get("confidence_score"),
            "price": scraped_data.get("price"),
            "stock_status": scraped_data.get("stock_status")
        }
        
        record = logger.makeRecord(
            logger.name, logging.INFO, __file__, 0,
            f"Successfully completed crawling task: {task_id}",
            (), None
        )
        record.extra_fields = extra_fields
        logger.handle(record)
    
    def log_crawl_error(self, logger: logging.Logger, task_id: str, 
                       error: Exception, retry_count: int) -> None:
        """크롤링 에러 로그"""
        extra_fields = {
            "event_type": "crawl_error",
            "task_id": task_id,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "retry_count": retry_count
        }
        
        record = logger.makeRecord(
            logger.name, logging.ERROR, __file__, 0,
            f"Crawling task failed: {task_id} - {str(error)}",
            (), exc_info=(type(error), error, error.__traceback__)
        )
        record.extra_fields = extra_fields
        logger.handle(record)
    
    def log_performance_metrics(self, logger: logging.Logger, metrics: Dict[str, Any]) -> None:
        """성능 메트릭 로그"""
        extra_fields = {
            "event_type": "performance_metrics",
            **metrics
        }
        
        record = logger.makeRecord(
            logger.name, logging.INFO, __file__, 0,
            "Performance metrics collected",
            (), None
        )
        record.extra_fields = extra_fields
        logger.handle(record)


# 전역 로거 인스턴스
crawler_logger = CrawlerLogger()


def get_logger(name: str) -> logging.Logger:
    """로거 획득 함수"""
    return crawler_logger.get_logger(name)


def setup_logging() -> None:
    """로깅 시스템 초기화"""
    global crawler_logger
    crawler_logger = CrawlerLogger()
    
    logger = get_logger(__name__)
    logger.info("Logging system initialized")


# 편의 함수들
def log_crawl_start(task_data: Dict[str, Any]) -> None:
    """크롤링 시작 로그 (편의 함수)"""
    logger = get_logger("crawler.task")
    crawler_logger.log_crawl_start(logger, task_data)


def log_crawl_success(task_id: str, scraped_data: Dict[str, Any], execution_time: float) -> None:
    """크롤링 성공 로그 (편의 함수)"""
    logger = get_logger("crawler.task")
    crawler_logger.log_crawl_success(logger, task_id, scraped_data, execution_time)


def log_crawl_error(task_id: str, error: Exception, retry_count: int) -> None:
    """크롤링 에러 로그 (편의 함수)"""
    logger = get_logger("crawler.task")
    crawler_logger.log_crawl_error(logger, task_id, error, retry_count)


def log_performance_metrics(metrics: Dict[str, Any]) -> None:
    """성능 메트릭 로그 (편의 함수)"""
    logger = get_logger("crawler.performance")
    crawler_logger.log_performance_metrics(logger, metrics)