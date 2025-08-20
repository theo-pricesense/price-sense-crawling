"""
Configuration settings for Price Sense crawler system.
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """데이터베이스 연결 설정"""
    
    url: str = Field(
        default="postgresql://username:password@localhost:5432/pricesense",
        description="PostgreSQL 데이터베이스 연결 URL"
    )
    pool_size: int = Field(default=20, description="연결 풀 크기")
    max_overflow: int = Field(default=10, description="최대 오버플로우 연결 수")
    pool_timeout: int = Field(default=30, description="연결 풀 타임아웃 (초)")
    pool_recycle: int = Field(default=3600, description="연결 재사용 주기 (초)")
    echo: bool = Field(default=False, description="SQL 쿼리 로깅 여부")

    model_config = SettingsConfigDict(
        env_prefix="DATABASE_",
        env_file=".env",
        case_sensitive=False
    )


class RedisSettings(BaseSettings):
    """Redis 연결 설정"""
    
    url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis 서버 연결 URL"
    )
    max_connections: int = Field(default=50, description="최대 연결 수")
    socket_timeout: int = Field(default=30, description="소켓 타임아웃 (초)")
    socket_connect_timeout: int = Field(default=10, description="연결 타임아웃 (초)")
    retry_on_timeout: bool = Field(default=True, description="타임아웃 시 재시도")
    health_check_interval: int = Field(default=30, description="헬스체크 주기 (초)")
    
    # 큐 설정
    crawl_queue_name: str = Field(default="pricesense:crawl:queue", description="크롤링 작업 큐 이름")
    result_queue_name: str = Field(default="pricesense:result:queue", description="결과 큐 이름")
    dead_letter_queue: str = Field(default="pricesense:dead:queue", description="실패 작업 큐 이름")
    
    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env",
        case_sensitive=False
    )


class CrawlerSettings(BaseSettings):
    """크롤링 관련 설정"""
    
    max_workers: int = Field(default=10, description="최대 병렬 크롤링 프로세스 수")
    request_delay: tuple[int, int] = Field(default=(1, 5), description="요청 간격 (최소, 최대 초)")
    max_retries: int = Field(default=3, description="최대 재시도 횟수")
    retry_delay: int = Field(default=60, description="재시도 지연 시간 (초)")
    timeout: int = Field(default=30, description="HTTP 요청 타임아웃 (초)")
    
    # User-Agent 설정
    user_agent_rotation: bool = Field(default=True, description="User-Agent 로테이션 사용")
    custom_user_agents: list[str] = Field(default=[], description="커스텀 User-Agent 목록")
    
    # 데이터 품질
    min_confidence_score: float = Field(default=0.7, description="최소 신뢰도 점수")
    duplicate_check_window: int = Field(default=600, description="중복 체크 윈도우 (초)")
    
    model_config = SettingsConfigDict(
        env_prefix="CRAWLER_",
        env_file=".env",
        case_sensitive=False
    )


class LoggingSettings(BaseSettings):
    """로깅 설정"""
    
    level: str = Field(default="INFO", description="로그 레벨")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="로그 포맷"
    )
    file_path: Optional[str] = Field(default=None, description="로그 파일 경로")
    max_file_size: int = Field(default=10 * 1024 * 1024, description="최대 로그 파일 크기 (bytes)")
    backup_count: int = Field(default=5, description="백업 로그 파일 수")
    
    # 구조화된 로깅
    json_logging: bool = Field(default=True, description="JSON 형태 로깅")
    include_trace: bool = Field(default=True, description="트레이스 정보 포함")
    
    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        env_file=".env",
        case_sensitive=False
    )


class SecuritySettings(BaseSettings):
    """보안 관련 설정"""
    
    chrome_driver_path: str = Field(
        default="/usr/local/bin/chromedriver",
        description="Chrome WebDriver 경로"
    )
    headless_mode: bool = Field(default=True, description="Headless 브라우저 모드")
    disable_images: bool = Field(default=True, description="이미지 로딩 비활성화")
    disable_css: bool = Field(default=True, description="CSS 로딩 비활성화")
    
    # Proxy 설정
    proxy_enabled: bool = Field(default=False, description="프록시 사용 여부")
    proxy_list: list[str] = Field(default=[], description="프록시 서버 목록")
    proxy_rotation: bool = Field(default=False, description="프록시 로테이션")
    
    model_config = SettingsConfigDict(
        env_prefix="SECURITY_",
        env_file=".env",
        case_sensitive=False
    )


class Settings(BaseSettings):
    """전체 애플리케이션 설정"""
    
    app_name: str = Field(default="Price Sense Crawler", description="애플리케이션 이름")
    app_version: str = Field(default="1.0.0", description="애플리케이션 버전")
    debug: bool = Field(default=False, description="디버그 모드")
    
    # 서브 설정들
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    crawler: CrawlerSettings = Field(default_factory=CrawlerSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False
    )


# 전역 설정 인스턴스
settings = Settings()