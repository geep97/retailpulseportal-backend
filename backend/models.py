from sqlalchemy import Column, Integer, String, TIMESTAMP, func
from database import Base


class User(Base):
    __tablename__ = "profiles"

    id = Column(String, primary_key=True, index=True)  # changed Integer to String
    username = Column(String, nullable=False)
    role = Column(String, nullable=False)
    store_id = Column(Integer, nullable=True)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    auth_provider_id = Column(String, nullable=True)