"""Allow closed conversations without introducing another inbox schema."""
from alembic import op
import sqlalchemy as sa

revision = "d05f234b7e64"
down_revision = "c94e123a6d53"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("conversations") as batch:
        batch.drop_constraint("ck_conversation_status", type_="check")
        batch.create_check_constraint("ck_conversation_status", "status IN ('AI','WAITING_HUMAN','HUMAN','CLOSED')")


def downgrade():
    op.execute(sa.text("UPDATE conversations SET status = 'HUMAN' WHERE status = 'CLOSED'"))
    with op.batch_alter_table("conversations") as batch:
        batch.drop_constraint("ck_conversation_status", type_="check")
        batch.create_check_constraint("ck_conversation_status", "status IN ('AI','WAITING_HUMAN','HUMAN')")
