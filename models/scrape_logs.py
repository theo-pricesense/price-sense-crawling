"""
Scrape logs model for tracking crawler execution results.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ProductScrapeLog(Base):
    """상품 크롤링 로그 모델"""
    
    __tablename__ = "product_scrape_logs"
    
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), 
        primary_key=True, 
        default=lambda: str(__import__('uuid').uuid4())
    )
    
    product_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("products.id"),
        nullable=False
    )
    
    # 실행 결과
    status: Mapped[str] = mapped_column(
        String(20), 
        nullable=False,
        comment="success, failed, timeout, partial"
    )
    
    # 수집된 데이터 (성공 시)
    scraped_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    
    # 오류 정보 (실패 시)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    
    # 성능 메트릭
    response_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        comment="응답 시간 (밀리초)"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.utcnow()
    )
    
    # 관계 설정
    product = relationship("Product", back_populates="scrape_logs")
    
    # 인덱스
    __table_args__ = (
        Index('idx_scrape_logs_product_id', 'product_id'),
        Index('idx_scrape_logs_status', 'status'),
        Index('idx_scrape_logs_created_at', 'created_at'),
        Index('idx_scrape_logs_product_status', 'product_id', 'status'),
    )
    
    def __repr__(self) -> str:
        return f"<ProductScrapeLog(product_id={self.product_id}, status={self.status}, created_at={self.created_at})>"