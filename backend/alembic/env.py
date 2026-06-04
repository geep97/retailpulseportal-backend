import os
import sys
from logging.config import fileConfig

# Import create_engine and your connection string
from sqlalchemy import create_engine
from alembic import context

# Fix the path to ensure we can import your models and database
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models import Base
from database import SQLALCHEMY_DATABASE_URL

# This is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=SQLALCHEMY_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode using the dynamic engine."""
    # Create the engine directly from your database.py variable
    connectable = create_engine(SQLALCHEMY_DATABASE_URL)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()