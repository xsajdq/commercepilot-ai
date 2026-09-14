"""phase 11: add listing_publish recommendation type

Revision ID: c1c9f3b6a2d4
Revises: aa22fd97e7bf
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c1c9f3b6a2d4'
down_revision: Union[str, None] = 'aa22fd97e7bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# SQLAlchemy's Enum(python_enum_class) stores each member's *name*, not
# its .value, in Postgres by default (see recommendation.py) - the
# existing type already holds 'PRICE_CHANGE', 'CONTENT_UPDATE', etc., so
# the new value must match that same convention.
_NEW_VALUE = "LISTING_PUBLISH"
_OLD_VALUES = ("PRICE_CHANGE", "CONTENT_UPDATE", "CATALOG_FIX", "STOCK_ALERT", "OTHER")


def upgrade() -> None:
    # Postgres 12+ allows ADD VALUE inside a transaction as long as the
    # new value isn't used by a statement in that same transaction -
    # true here, this migration only adds it.
    op.execute(f"ALTER TYPE recommendation_type ADD VALUE '{_NEW_VALUE}'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE - the standard workaround
    # is to recreate the enum type without the value and swap the column
    # over. Any row already using LISTING_PUBLISH would break this cast;
    # that's an accepted risk for downgrading past the phase that
    # introduced the value in the first place, same as any other enum
    # rollback.
    old_values_sql = ", ".join(f"'{v}'" for v in _OLD_VALUES)
    op.execute("ALTER TYPE recommendation_type RENAME TO recommendation_type_old")
    op.execute(f"CREATE TYPE recommendation_type AS ENUM ({old_values_sql})")
    op.execute(
        "ALTER TABLE recommendations "
        "ALTER COLUMN type TYPE recommendation_type "
        "USING type::text::recommendation_type"
    )
    op.execute("DROP TYPE recommendation_type_old")
