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
        ("campaigns", "listener_api_key"): "ALTER TABLE campaigns ADD COLUMN listener_api_key VARCHAR",
        ("campaigns", "listener_api_key_hash"): "ALTER TABLE campaigns ADD COLUMN listener_api_key_hash VARCHAR",
        ("campaigns", "listener_api_key_last_four"): "ALTER TABLE campaigns ADD COLUMN listener_api_key_last_four VARCHAR",
        ("campaigns", "brand_voice_profile"): "ALTER TABLE campaigns ADD COLUMN brand_voice_profile JSON",
        ("campaigns", "brand_context_profile"): "ALTER TABLE campaigns ADD COLUMN brand_context_profile JSON",
        ("campaigns", "listener_config"): "ALTER TABLE campaigns ADD COLUMN listener_config JSON",
        ("campaigns", "listener_status"): "ALTER TABLE campaigns ADD COLUMN listener_status VARCHAR DEFAULT 'stopped'",
        ("campaigns", "listener_started_at"): "ALTER TABLE campaigns ADD COLUMN listener_started_at DATETIME",
        ("campaigns", "listener_last_polled_at"): "ALTER TABLE campaigns ADD COLUMN listener_last_polled_at DATETIME",
        ("campaigns", "approved_response_count"): "ALTER TABLE campaigns ADD COLUMN approved_response_count INTEGER DEFAULT 0",
        ("queries", "channel"): "ALTER TABLE queries ADD COLUMN channel VARCHAR DEFAULT 'mcp'",
        ("matches", "channel"): "ALTER TABLE matches ADD COLUMN channel VARCHAR DEFAULT 'mcp'",
        ("clicks", "channel"): "ALTER TABLE clicks ADD COLUMN channel VARCHAR DEFAULT 'mcp'",
        ("clicks", "source"): "ALTER TABLE clicks ADD COLUMN source VARCHAR DEFAULT 'mcp'",
        ("clicks", "surface"): "ALTER TABLE clicks ADD COLUMN surface VARCHAR",
        ("clicks", "response_id"): "ALTER TABLE clicks ADD COLUMN response_id VARCHAR",
        ("conversions", "channel"): "ALTER TABLE conversions ADD COLUMN channel VARCHAR DEFAULT 'mcp'",
    }

    with engine.begin() as connection:
        if "agent_events" not in table_columns:
            connection.execute(
                text(
                    """
                    CREATE TABLE agent_events (
                        id VARCHAR PRIMARY KEY,
                        campaign_id VARCHAR NOT NULL,
                        event_type VARCHAR NOT NULL,
                        category VARCHAR,
                        surface VARCHAR,
                        description TEXT NOT NULL,
                        source_url TEXT,
                        source_content TEXT,
                        source_author VARCHAR,
                        target_audience TEXT,
                        product_id VARCHAR,
                        referral_url TEXT,
                        response_text TEXT,
                        tokens_used INTEGER DEFAULT 0,
                        compute_cost_usd FLOAT DEFAULT 0,
                        expected_impact VARCHAR,
                        details JSON,
                        created_at DATETIME
                    )
                    """
                )
            )
            table_columns["agent_events"] = {
                "id",
                "campaign_id",
                "event_type",
                "category",
                "surface",
                "description",
                "source_url",
                "source_content",
                "source_author",
                "target_audience",
                "product_id",
                "referral_url",
                "response_text",
                "tokens_used",
                "compute_cost_usd",
                "expected_impact",
                "details",
                "created_at",
            }

        for (table_name, column_name), statement in alter_statements.items():
            if table_name in table_columns and column_name not in table_columns[table_name]:
                connection.execute(text(statement))

        if "agent_events" in table_columns or "agent_events" in inspector.get_table_names():
            agent_event_columns = table_columns.get("agent_events", set())
            if "details" not in agent_event_columns:
                connection.execute(text("ALTER TABLE agent_events ADD COLUMN details JSON"))
            connection.execute(text("UPDATE agent_events SET details = '{}' WHERE details IS NULL"))

        for table_name in ("queries", "matches", "clicks", "conversions"):
            if table_name in table_columns or table_name in inspector.get_table_names():
                connection.execute(
                    text(f"UPDATE {table_name} SET channel = 'mcp' WHERE channel IS NULL")
                )

        if "clicks" in table_columns or "clicks" in inspector.get_table_names():
            connection.execute(text("UPDATE clicks SET source = 'mcp' WHERE source IS NULL"))

        if "campaigns" in table_columns or "campaigns" in inspector.get_table_names():
            connection.execute(
                text("UPDATE campaigns SET listener_status = 'stopped' WHERE listener_status IS NULL")
            )
            connection.execute(
                text("UPDATE campaigns SET approved_response_count = 0 WHERE approved_response_count IS NULL")
            )
            connection.execute(
                text("UPDATE campaigns SET brand_voice_profile = '{}' WHERE brand_voice_profile IS NULL")
            )
            connection.execute(
                text("UPDATE campaigns SET brand_context_profile = '{}' WHERE brand_context_profile IS NULL")
            )
            connection.execute(
                text("UPDATE campaigns SET listener_config = '{}' WHERE listener_config IS NULL")
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
