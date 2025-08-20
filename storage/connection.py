"""
Database connection management for Price Sense crawler system.
"""

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator
import logging

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncSession, 
    create_async_engine, 
    async_sessionmaker
)
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from config.settings import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """데이터베이스 연결 관리자"""
    
    def __init__(self):
        self._engine: Engine = None
        self._async_engine = None
        self._session_factory: sessionmaker = None
        self._async_session_factory = None
        self._initialized = False
    
    def initialize(self) -> None:
        """데이터베이스 연결 초기화"""
        if self._initialized:
            return
            
        try:
            # 동기 엔진 생성
            self._engine = create_engine(
                settings.database.url,
                pool_size=settings.database.pool_size,
                max_overflow=settings.database.max_overflow,
                pool_timeout=settings.database.pool_timeout,
                pool_recycle=settings.database.pool_recycle,
                pool_pre_ping=True,  # 연결 상태 확인
                poolclass=QueuePool,
                echo=settings.database.echo
            )
            
            # 비동기 엔진 생성 (향후 확장용)
            async_url = settings.database.url.replace("postgresql://", "postgresql+asyncpg://")
            self._async_engine = create_async_engine(
                async_url,
                pool_size=settings.database.pool_size,
                max_overflow=settings.database.max_overflow,
                pool_timeout=settings.database.pool_timeout,
                pool_recycle=settings.database.pool_recycle,
                echo=settings.database.echo
            )
            
            # 세션 팩토리 생성
            self._session_factory = sessionmaker(
                bind=self._engine,
                autocommit=False,
                autoflush=False
            )
            
            self._async_session_factory = async_sessionmaker(
                bind=self._async_engine,
                class_=AsyncSession,
                autocommit=False,
                autoflush=False
            )
            
            # 엔진 이벤트 리스너 등록
            self._register_event_listeners()
            
            self._initialized = True
            logger.info("Database connection initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database connection: {e}")
            raise
    
    def _register_event_listeners(self) -> None:
        """SQLAlchemy 이벤트 리스너 등록"""
        
        @event.listens_for(self._engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            """연결 시 PostgreSQL 설정"""
            if "postgresql" in settings.database.url:
                with dbapi_connection.cursor() as cursor:
                    cursor.execute("SET timezone='UTC'")
                    cursor.execute("SET statement_timeout='30s'")
        
        @event.listens_for(self._engine, "checkout")
        def receive_checkout(dbapi_connection, connection_record, connection_proxy):
            """연결 풀에서 연결을 가져올 때"""
            logger.debug("Connection checked out from pool")
        
        @event.listens_for(self._engine, "checkin")
        def receive_checkin(dbapi_connection, connection_record):
            """연결 풀에 연결을 반환할 때"""
            logger.debug("Connection returned to pool")
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """동기 데이터베이스 세션 컨텍스트 매니저"""
        if not self._initialized:
            self.initialize()
            
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """비동기 데이터베이스 세션 컨텍스트 매니저"""
        if not self._initialized:
            self.initialize()
            
        session = self._async_session_factory()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Async database session error: {e}")
            raise
        finally:
            await session.close()
    
    def get_engine(self) -> Engine:
        """동기 엔진 반환"""
        if not self._initialized:
            self.initialize()
        return self._engine
    
    def get_async_engine(self):
        """비동기 엔진 반환"""
        if not self._initialized:
            self.initialize()
        return self._async_engine
    
    def check_connection(self) -> bool:
        """데이터베이스 연결 상태 확인"""
        try:
            with self.get_session() as session:
                session.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False
    
    def close(self) -> None:
        """데이터베이스 연결 종료"""
        if self._engine:
            self._engine.dispose()
            logger.info("Database engine disposed")
        
        if self._async_engine:
            # asyncio.run을 사용하지 않고 직접 처리
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._async_engine.dispose())
            else:
                asyncio.run(self._async_engine.dispose())
            logger.info("Async database engine disposed")
        
        self._initialized = False


# 전역 데이터베이스 매니저 인스턴스
db_manager = DatabaseManager()


# 편의 함수들
def get_db_session() -> Generator[Session, None, None]:
    """데이터베이스 세션 획득 (동기)"""
    return db_manager.get_session()


async def get_async_db_session() -> AsyncGenerator[AsyncSession, None]:
    """데이터베이스 세션 획득 (비동기)"""
    async with db_manager.get_async_session() as session:
        yield session


def init_db() -> None:
    """데이터베이스 연결 초기화"""
    db_manager.initialize()


def close_db() -> None:
    """데이터베이스 연결 종료"""
    db_manager.close()