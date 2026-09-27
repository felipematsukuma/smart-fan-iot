from sqlalchemy import Boolean, Column, Float, Integer, String
from app.database import Base

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(100), default="Ventilador do Quarto")
    is_on = Column(Boolean, default=False)
    kwh_rate = Column(Float, default=0.85)  # Custo da tarifa (ex: R$ 0,85 / kWh)
    auto_off_time = Column(String(5), nullable=True)  # Formato "HH:MM", ex: "03:30"
    auto_off_enabled = Column(Boolean, default=False)