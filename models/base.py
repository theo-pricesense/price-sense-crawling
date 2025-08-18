"""
Base model classes and enums for the Price Sense crawler system.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class PlatformType(str, Enum):
    """이커머스 플랫폼 타입"""
    COUPANG = "coupang"
    NAVER_SHOPPING = "naver_shopping"
    ELEVEN_ST = "eleven_st"
    SMART_STORE = "smart_store"
    GMARKET = "gmarket"
    SSG = "ssg"
    WEMAKEPRICE = "wemakeprice"
    TMON = "tmon"


class ProductStatus(str, Enum):
    """상품 상태"""
    ACTIVE = "active"           # 정상 추적 중
    INACTIVE = "inactive"       # 추적 일시 중지
    FAILED = "failed"           # 수집 실패
    DISCONTINUED = "discontinued"  # 단종/삭제된 상품
    BLOCKED = "blocked"         # 플랫폼에서 차단


class StockStatus(str, Enum):
    """재고 상태"""
    AVAILABLE = "available"      # 구매 가능
    LIMITED = "limited"          # 수량 제한
    CRITICAL = "critical"        # 품절 임박
    OUT_OF_STOCK = "out_of_stock"  # 품절
    PREORDER = "preorder"        # 예약 주문
    UNKNOWN = "unknown"          # 확인 불가


Base = declarative_base()


class BaseModel:
    """공통 기본 모델 믹스인"""
    
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), 
        primary_key=True, 
        default=lambda: str(uuid4())
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )