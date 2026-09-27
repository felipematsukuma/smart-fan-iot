from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from app.config import settings

# Conexão PostgreSQL
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Conexão InfluxDB
influx_client = InfluxDBClient(
    url=settings.INFLUXDB_URL,
    token=settings.INFLUXDB_TOKEN,
    org=settings.INFLUXDB_ORG
)
# Telemetria é enviada a 0,5 Hz. O modo síncrono garante que o ponto foi
# persistido antes de o backend confirmar o recebimento via WebSocket.
write_api = influx_client.write_api(write_options=SYNCHRONOUS)
query_api = influx_client.query_api()