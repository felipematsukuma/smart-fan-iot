"""Persistent per-device configuration and last observed relay state."""

from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), default="Ventilador do Quarto")
    is_on: Mapped[bool] = mapped_column(Boolean, default=False)
    kwh_rate: Mapped[float] = mapped_column(Float, default=0.85)
    auto_off_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    auto_off_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
