from sqlalchemy import Column, Integer, String, TIMESTAMP, func
from database import Base

class User(Base):
    __tablename__ = "profiles"
    id = Column(String, primary_key=True, index=True)
    username = Column(String, nullable=False)
    role = Column(String, nullable=False)
    store_id = Column(Integer, nullable=True)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    auth_provider_id = Column(String, nullable=True)

class AuditLog(Base):
    __tablename__ = "audit_log"
    audit_id = Column(Integer, primary_key=True)

class Product(Base):
    __tablename__ = "product"
    product_id = Column(Integer, primary_key=True)
    product_name = Column(String, nullable=False)
    unit_price = Column(Integer, nullable=False)
    category = Column(String)

class Store(Base):
    __tablename__ = "stores"
    store_id = Column(Integer, primary_key=True)

class Customer(Base):
    __tablename__ = "customers"
    customer_id = Column(Integer, primary_key=True)

class Inventory(Base):
    __tablename__ = "inventory"
    inventory_id = Column(Integer, primary_key=True)

class Transaction(Base):
    __tablename__ = "transactions"
    transaction_id = Column(Integer, primary_key=True)

class Submission(Base):
    __tablename__ = "submissions"
    submission_id = Column(Integer, primary_key=True)

class IntegrityLog(Base):
    __tablename__ = "integrity_log"
    log_id = Column(Integer, primary_key=True)