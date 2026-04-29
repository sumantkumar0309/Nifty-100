import pandas as pd
from sqlalchemy import create_engine
engine = create_engine('postgresql+psycopg2://postgres:postgres@localhost:5432/nifty100')
with engine.connect() as conn:
    tables = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'").fetchall()
    for t in tables:
        count = conn.execute(f"SELECT count(*) FROM {t[0]}").scalar()
        print(f"Table {t[0]}: {count} rows")

