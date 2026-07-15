import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData, Table, Column
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import String, Text, DateTime, TIMESTAMP, Boolean

load_dotenv()
SKIP_TABLES = {"users", "alembic_version"}


PG_URL = os.getenv("DATABASE_URL")
if not PG_URL:
    raise RuntimeError("DATABASE_URL not found in .env — this should be your Supabase Postgres connection string.")

MSSQL_URL = (
    r"mssql+pyodbc://@(localdb)\MSSQLLocalDB/RetailPulseGH"
    r"?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"
)

source_engine = create_engine(PG_URL)
target_engine = create_engine(MSSQL_URL)


def convert_type(col_type):

    if isinstance(col_type, postgresql.UUID):
        return String(36)
    if isinstance(col_type, (postgresql.JSONB, postgresql.JSON)):
        return Text()
    if isinstance(col_type, postgresql.ARRAY):
        return Text()
    if isinstance(col_type, TIMESTAMP):

        return DateTime()
    if isinstance(col_type, postgresql.BOOLEAN):
        return Boolean()
    return col_type


def main():
    print("Reflecting live schema from Supabase Postgres...")
    source_meta = MetaData()
    source_meta.reflect(bind=source_engine)

    all_tables = source_meta.sorted_tables
    tables_in_order = [t for t in all_tables if t.name not in SKIP_TABLES]
    skipped = [t.name for t in all_tables if t.name in SKIP_TABLES]

    print(f"Found {len(all_tables)} tables total.")
    if skipped:
        print(f"Skipping (not app data): {skipped}")
    print(f"Migrating: {[t.name for t in tables_in_order]}\n")

    target_meta = MetaData()
    for table in tables_in_order:
        new_columns = []
        for col in table.columns:
            new_columns.append(Column(
                col.name,
                convert_type(col.type),
                primary_key=col.primary_key,
                nullable=col.nullable,
                autoincrement=False,
            ))
        Table(table.name, target_meta, *new_columns)

    print("Creating tables on local SQL Server (RetailPulseGH)...")
    target_meta.create_all(target_engine)
    print("Schema created.\n")

    print("Copying data...")
    with source_engine.connect() as src_conn, target_engine.connect() as tgt_conn:
        for table in tables_in_order:
            target_table = target_meta.tables[table.name]


            tgt_conn.execute(target_table.delete())
            tgt_conn.commit()

            rows = src_conn.execute(table.select()).mappings().all()
            if not rows:
                print(f"  {table.name}: 0 rows, skipping")
                continue
            tgt_conn.execute(target_table.insert(), [dict(r) for r in rows])
            tgt_conn.commit()
            print(f"  {table.name}: {len(rows)} rows migrated")

    print("\nMigration complete.")


if __name__ == "__main__":
    main()