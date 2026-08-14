import os
import sys
import glob
import asyncio
import asyncpg

# Add parent directory and api directory to path for configuration imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings

async def run_migrations():
    print(f"Connecting to PostgreSQL database '{settings.POSTGRES_DB}' at {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}...")
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )

    try:
        # Create schema_migrations table if not exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(128) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
            );
        """)

        migrations_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "migrations"))
        sql_files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))

        if not sql_files:
            print("No migration SQL files found.")
            return

        for sql_file in sql_files:
            filename = os.path.basename(sql_file)
            applied = await conn.fetchval(
                "SELECT version FROM schema_migrations WHERE version = $1", filename
            )
            if applied:
                print(f"[SKIP] Migration '{filename}' is already applied.")
                continue

            print(f"[APPLYING] Migration '{filename}'...")
            with open(sql_file, "r", encoding="utf-8") as f:
                sql_script = f.read()

            async with conn.transaction():
                await conn.execute(sql_script)
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)", filename
                )
            print(f"[SUCCESS] Migration '{filename}' applied successfully.")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(run_migrations())
