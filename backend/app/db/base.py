"""Declarative base + model registry.

All models must be imported here so Alembic autogenerate and
create_all see every table.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


import app.models.conversation  # noqa: E402, F401
import app.models.document  # noqa: E402, F401
import app.models.message  # noqa: E402, F401
import app.models.user  # noqa: E402, F401
