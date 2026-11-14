"""conversation_messages: history as the person saw it (Part E #61)

`agents` (text[]) replaces `agent_type`: the old app's names map to the coaches,
"physical,nutrition" becomes a list, and the person's message, Holos's own reply and the
old coordinator have none. `display` holds what the person saw (C.5 History) and
`trace_id` the answer's request, so a held entry's card can follow its decision (C.17).
`warnings` was last written by the old app.

Revision ID: 4b5c6d7e8f96
Revises: 3a4b5c6d7e85
Create Date: 2026-11-14
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

from alembic import op

revision = "4b5c6d7e8f96"
down_revision = "3a4b5c6d7e85"
branch_labels = None
depends_on = None

# Each name the coaches have had, in the order a turn lists them
AGENTS = (("physical", ("physical", "physical-fitness")),
          ("nutrition", ("nutrition",)),
          ("mental", ("mental", "mental-fitness")))


def upgrade() -> None:
    op.add_column("conversation_messages", sa.Column("agents", ARRAY(sa.String()),
                                                     nullable=True))
    op.add_column("conversation_messages", sa.Column("display", sa.JSON(), nullable=True))
    op.add_column("conversation_messages", sa.Column("trace_id", sa.String(64),
                                                     nullable=True))
    # Each coach named in the old comma list, in the coaches' order; none left is null
    names = "string_to_array(replace(agent_type, ' ', ''), ',')"
    picked = ", ".join(
        f"CASE WHEN {names} && ARRAY[{', '.join(repr(n) for n in old)}]::text[] "
        f"THEN '{agent}' END" for agent, old in AGENTS)
    op.execute(f"UPDATE conversation_messages SET agents = NULLIF(array_remove("
               f"ARRAY[{picked}]::text[], NULL), '{{}}') WHERE role = 'assistant'")
    op.create_index("idx_conversation_user_trace", "conversation_messages",
                    ["user_id", "trace_id"])
    op.drop_column("conversation_messages", "agent_type")
    op.drop_column("conversation_messages", "warnings")


def downgrade() -> None:
    op.add_column("conversation_messages", sa.Column("warnings", sa.Text(), nullable=True))
    op.add_column("conversation_messages", sa.Column("agent_type", sa.String(),
                                                     nullable=True))
    op.execute("UPDATE conversation_messages SET agent_type = CASE "
               "WHEN role = 'user' THEN 'user' "
               "WHEN agents IS NULL THEN 'holos' "
               "ELSE array_to_string(agents, ',') END")
    op.alter_column("conversation_messages", "agent_type", nullable=False,
                    server_default="coordinator")
    op.drop_index("idx_conversation_user_trace", "conversation_messages")
    op.drop_column("conversation_messages", "trace_id")
    op.drop_column("conversation_messages", "display")
    op.drop_column("conversation_messages", "agents")
