import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from supabase import create_client, Client


load_dotenv()


SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
admin_supabase: Client = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)




DB_TARGET = os.getenv("DB_TARGET", "supabase")

if DB_TARGET == "local":
    SQLALCHEMY_DATABASE_URL = (
        r"mssql+pyodbc://@(localdb)\MSSQLLocalDB/RetailPulseGH"
        r"?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"
    )
else:
    SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()