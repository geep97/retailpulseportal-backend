from sqlalchemy import Column, Integer, String, TIMESTAMP, func
from database import Base


class User(Base):
    __tablename__ = "profiles"  # Pointing to the table you see in the dashboard

    # Map the columns exactly as they appear in Supabase
    # Assuming 'id' is your primary key
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False)
    role = Column(String, nullable=False)
    store_id = Column(Integer, nullable=True)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Now add your new column here:
    auth_provider_id = Column(String, nullable=True)