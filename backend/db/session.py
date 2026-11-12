from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.config import settings

if settings.database_url.startswith('sqlite:///'):
    dbpath=settings.database_url.removeprefix('sqlite:///')
    if dbpath not in {':memory:',''}:
        Path(dbpath).parent.mkdir(parents=True, exist_ok=True)
engine=create_engine(settings.database_url, future=True, pool_pre_ping=True, connect_args={'check_same_thread':False} if settings.database_backend=='sqlite' else {})
SessionLocal=sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)

@contextmanager
def session_scope():
    session=SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback(); raise
    finally:
        session.close()
