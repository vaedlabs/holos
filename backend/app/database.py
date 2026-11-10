"""The declarative base every model and Alembic share. Engines and sessions are in
`app.data.engine` (Plan C.1)."""

from sqlalchemy.orm import declarative_base

Base = declarative_base()
