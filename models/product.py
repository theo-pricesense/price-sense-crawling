"""
Product model for the Price Sense crawler system.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, 
    DECIMAL, String, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, BaseModel, PlatformType, ProductStatus, StockStatus


class Product(Base, BaseModel):
    """상품 모델"""
    
    __tablename__ = "products"
    
    # 사용자 정보
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), 
        ForeignKey("users.id"),
        nullable=False
    )
    
    # 플랫폼 정보
    platform: Mapped[PlatformType] = mapped_column(nullable=False)
    platform_product_id: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 기본 정보
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    custom_name: Mapped[Optional[str]] = mapped_column(String(500))
    current_price: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2))
    original_price: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="KRW")
    
    # 재고 신호 정보
    stock_status: Mapped[StockStatus] = mapped_column(default=StockStatus.UNKNOWN)
    stock_signals: Mapped[dict] = mapped_column(JSONB, default={})
    
    # 상품 상세
    description: Mapped[Optional[str]] = mapped_column(Text)
    brand: Mapped[Optional[str]] = mapped_column(String(100))
    image_urls: Mapped[List[str]] = mapped_column(JSONB, default=[])
    
    # 분류 정보
    category_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("product_categories.id")
    )
    group_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("product_groups.id")
    )
    tags: Mapped[List[str]] = mapped_column(ARRAY(String), default=[])
    
    # 상태 관리
    status: Mapped[ProductStatus] = mapped_column(default=ProductStatus.ACTIVE)
    tracking_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # 메타데이터
    last_scraped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    scrape_attempts: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # 옵션 정보
    options: Mapped[List[dict]] = mapped_column(JSONB, default=[])
    
    # 판매자 정보
    seller_info: Mapped[Optional[dict]] = mapped_column(JSONB)
    
    # 사용자 노트
    notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # 관계 설정
    price_history = relationship("PriceHistory", back_populates="product")
    stock_history = relationship("StockHistory", back_populates="product")
    scrape_logs = relationship("ProductScrapeLog", back_populates="product")
    
    # 제약 조건
    __table_args__ = (
        UniqueConstraint('user_id', 'platform', 'platform_product_id', 
                        name='uk_user_platform_product'),
        Index('idx_products_user_id', 'user_id'),
        Index('idx_products_platform', 'platform'),
        Index('idx_products_status', 'status'),
        Index('idx_products_tracking_enabled', 'tracking_enabled'),
        Index('idx_products_category_id', 'category_id'),
        Index('idx_products_group_id', 'group_id'),
        Index('idx_products_tags', 'tags'),
        Index('idx_products_created_at', 'created_at'),
        Index('idx_products_updated_at', 'updated_at'),
        Index('idx_products_last_scraped_at', 'last_scraped_at'),
    )
    
    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name={self.name[:50]}, platform={self.platform})>"


class ProductCategory(Base, BaseModel):
    """상품 카테고리 모델"""
    
    __tablename__ = "product_categories"
    
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("product_categories.id")
    )
    level: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id")
    )
    
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # 제약 조건
    __table_args__ = (
        UniqueConstraint('name', 'parent_id', name='uk_category_name_parent'),
        Index('idx_product_categories_parent_id', 'parent_id'),
        Index('idx_product_categories_level', 'level'),
        Index('idx_product_categories_is_system', 'is_system'),
    )


class ProductGroup(Base, BaseModel):
    """상품 그룹 모델"""
    
    __tablename__ = "product_groups"
    
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=False
    )
    
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    color: Mapped[Optional[str]] = mapped_column(String(7))  # HEX 색상 코드
    
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # 제약 조건
    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uk_user_group_name'),
        Index('idx_product_groups_user_id', 'user_id'),
    )