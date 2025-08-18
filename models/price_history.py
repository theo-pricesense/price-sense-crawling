"""
Price history model for tracking product price changes.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, DECIMAL, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class PriceHistory(Base):
    """가격 변동 이력 모델"""
    
    __tablename__ = "price_history"
    
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
    
    # 가격 정보
    price: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    discount_rate: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(5, 2))
    promotion_info: Mapped[Optional[str]] = mapped_column(Text)
    
    # 데이터 품질
    confidence_score: Mapped[Decimal] = mapped_column(
        DECIMAL(3, 2), 
        nullable=False,
        comment="데이터 추출 신뢰도 (0.00-1.00)"
    )
    
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.utcnow()
    )
    
    # 관계 설정
    product = relationship("Product", back_populates="price_history")
    
    # 인덱스
    __table_args__ = (
        Index('idx_price_history_product_id', 'product_id'),
        Index('idx_price_history_recorded_at', 'recorded_at'),
        Index('idx_price_history_product_recorded', 'product_id', 'recorded_at'),
        Index('idx_price_history_confidence', 'confidence_score'),
    )
    
    def __repr__(self) -> str:
        return f"<PriceHistory(product_id={self.product_id}, price={self.price}, recorded_at={self.recorded_at})>"