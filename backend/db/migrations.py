from sqlalchemy import inspect, text
from backend.db.base import Base
from backend.db.session import engine


EXPECTED_HEAD_REVISION = '20261108_0010'


def expected_head_revision(): return EXPECTED_HEAD_REVISION


def current_database_revision(_engine=engine):
    try:
        with _engine.connect() as c:
            if 'alembic_version' not in inspect(_engine).get_table_names(): return None
            return c.execute(text('SELECT version_num FROM alembic_version')).scalar()
    except Exception: return None


def create_all():
    from backend.db import models  # noqa
    try:
        from backend.uploads import models as upload_models  # noqa
    except Exception:
        pass
    Base.metadata.create_all(engine)
