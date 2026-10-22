from alembic import context

from workbench.persistence import Base

connection = context.config.attributes.get("connection")
if connection is None:
    from workbench.config import Settings
    from sqlalchemy import create_engine

    engine = create_engine(Settings.from_env().database_url)
    connection = engine.connect()

context.configure(connection=connection, target_metadata=Base.metadata)
with context.begin_transaction():
    context.run_migrations()
