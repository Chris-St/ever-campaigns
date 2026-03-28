from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine_kwargs: dict = {}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, future=True, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def init_db() -> None:
    from app.models import entities  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()


def ensure_runtime_schema() -> None:
    inspector = inspect(engine)
    table_columns = {
        table_name: {column["name"] for column in inspector.get_columns(table_name)}
        for table_name in inspector.get_table_names()
    }

    alter_statements = {
        ("merchants", "merchant_slug"): "ALTER TABLE merchants ADD COLUMN merchant_slug VARCHAR",
        ("queries", "channel"): "ALTER TABLE queries ADD COLUMN channel VARCHAR DEFAULT 'mcp'",
        ("matches", "channel"): "ALTER TABLE matches ADD COLUMN channel VARCHAR DEFAULT 'mcp'",
        ("clicks", "channel"): "ALTER TABLE clicks ADD COLUMN channel VARCHAR DEFAULT 'mcp'",
        ("conversions", "channel"): "ALTER TABLE conversions ADD COLUMN channel VARCHAR DEFAULT 'mcp'",
    }

    with engine.begin() as connection:
        for (table_name, column_name), statement in alter_statements.items():
            if table_name in table_columns and column_name not in table_columns[table_name]:
                connection.execute(text(statement))

        for table_name in ("queries", "matches", "clicks", "conversions"):
            if table_name in table_columns or table_name in inspector.get_table_names():
                connection.execute(
                    text(f"UPDATE {table_name} SET channel = 'mcp' WHERE channel IS NULL")
                )

    backfill_merchant_slugs()


def backfill_merchant_slugs() -> None:
    from sqlalchemy import select

    from app.models.entities import Merchant
    from app.services.endpoints import assign_merchant_slug

    db = SessionLocal()
    try:
        merchants = db.scalars(select(Merchant)).all()
        dirty = False
        for merchant in merchants:
            if merchant.merchant_slug:
                continue
            assign_merchant_slug(db, merchant)
            dirty = True
        if dirty:
            db.commit()
    finally:
        db.close()
