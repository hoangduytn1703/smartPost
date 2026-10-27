from sqlmodel import Session, SQLModel, create_engine

from . import config

_engine = None


def engine():
    global _engine
    if _engine is None:
        config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{config.DB_PATH}", connect_args={"check_same_thread": False}
        )
        from . import models  # noqa: F401  (register tables)

        SQLModel.metadata.create_all(_engine)
    return _engine


def session() -> Session:
    return Session(engine(), expire_on_commit=False)
