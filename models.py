from sqlalchemy import Column, Integer, String, TIMESTAMP, Date, Numeric, Text, Boolean, func
from database import Base


class User(Base):
    __tablename__ = "profiles"
    id = Column(String, primary_key=True, index=True)
    username = Column(String, nullable=False)
    role = Column(String, nullable=False)
    store_id = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    auth_provider_id = Column(String, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    audit_id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=True)
    action = Column(String, nullable=True)
    target_table = Column(String, nullable=True)
    target_id = Column(String, nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())


class Product(Base):
    __tablename__ = "product"
    product_id = Column(Integer, primary_key=True)
    product_name = Column(String, nullable=False)
    unit_price = Column(Numeric, nullable=False)
    category = Column(String)


class Store(Base):
    __tablename__ = "stores"
    store_id = Column(Integer, primary_key=True)
    store_name = Column(String, nullable=False)
    location = Column(String, nullable=True)


class Customer(Base):
    __tablename__ = "customers"
    customer_id = Column(Integer, primary_key=True)


class Inventory(Base):
    __tablename__ = "inventory"
    inventory_id = Column(Integer, primary_key=True)
    store_id = Column(Integer, nullable=False)
    product_id = Column(Integer, nullable=False)
    stock_quantity = Column(Integer, nullable=False)
    reorder_level = Column(Integer, nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"
    transaction_id   = Column(Integer, primary_key=True)  # NOT NULL
    submission_id    = Column(Integer, nullable=False)     # NOT NULL
    store_id         = Column(Integer, nullable=False)     # NOT NULL
    product_id       = Column(Integer, nullable=False)     # NOT NULL
    customer_id      = Column(Integer, nullable=True)
    transaction_date = Column(Date,    nullable=True)
    quantity         = Column(Integer, nullable=False)     # NOT NULL
    unit_price       = Column(Numeric, nullable=False)     # NOT NULL
    total_price      = Column(Numeric, nullable=False)     # NOT NULL
    payment_method   = Column(String,  nullable=False)     # NOT NULL

class Submission(Base):
    __tablename__ = "submissions"
    submission_id = Column(Integer, primary_key=True)   # NOT NULL
    store_id      = Column(Integer, nullable=False)     # NOT NULL
    week_label    = Column(String,  nullable=False)     # NOT NULL  e.g. "Week 24 · Jun 2026"
    period_year   = Column(Integer, nullable=False)     # NOT NULL  ISO year
    period_month  = Column(Integer, nullable=True)      # calendar month (1-12)
    week_start    = Column(Date,    nullable=True)      # Monday that opens the week
    week_end      = Column(Date,    nullable=True)      # Sunday that closes the week
    submitted_at  = Column(TIMESTAMP, nullable=True)
    filename      = Column(String,  nullable=True)      # original uploaded filename
    status        = Column(String,  nullable=True)      # "active" | "inactive"
    submitted_by  = Column(String,  nullable=True)      # user UUID

class IntegrityLog(Base):
    __tablename__ = "integrity_log"
    log_id          = Column(Integer, primary_key=True)   # NOT NULL
    submission_id   = Column(Integer, nullable=False)     # NOT NULL
    total_received  = Column(Integer, nullable=True)
    total_included  = Column(Integer, nullable=True)
    total_excluded  = Column(Integer, nullable=True)
    total_fixed     = Column(Integer, nullable=True)
    exclusion_notes = Column(Text,    nullable=True)
    fix_notes       = Column(Text,    nullable=True)
    logged_at       = Column(TIMESTAMP, nullable=True)