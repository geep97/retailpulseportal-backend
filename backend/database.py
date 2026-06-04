import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# --- Supabase SDK Setup ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")           # Public Anon Key
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") # Secret Key

# Client for public/auth actions (Login)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Client for admin actions (User creation)
admin_supabase: Client = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)

# --- SQLAlchemy Setup ---
db_password = os.getenv("SUPABASE_PASSWORD")
db_id = os.getenv("SUPABASE_ID")
SQLALCHEMY_DATABASE_URL = f"postgresql://postgres:{db_password}@db.{db_id}.supabase.co:5432/postgres"

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()