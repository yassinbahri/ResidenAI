"""allow reverted content in document version history

Revision ID: 4c8b1e9f27a3
Revises: 17f81db6cc5a
Create Date: 2026-07-30 00:00:00.000000

Drops UNIQUE(source_id, normalized_sha256). Vendors revert wording - a
residency claim appears, is pulled, then reinstated - and that timeline cannot
be expressed by a content-addressed uniqueness rule: the reappearing hash
collides with its own earlier row and check_source raised IntegrityError,
which aborted the entire scheduler tick. Replaced with a plain index on
(source_id, created_at), which is how every read of this table is shaped.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '4c8b1e9f27a3'
down_revision: Union[str, None] = '17f81db6cc5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        'document_versions_source_id_normalized_sha256_key',
        'document_versions',
        type_='unique',
    )
    op.create_index(
        'ix_document_versions_source_created',
        'document_versions',
        ['source_id', 'created_at'],
    )


def downgrade() -> None:
    # Re-adding the constraint fails if any source already has a reverted
    # (duplicate-hash) version, which is exactly the state this migration
    # permits. Deduplicate first if you really need to go back.
    op.drop_index('ix_document_versions_source_created', table_name='document_versions')
    op.create_unique_constraint(
        'document_versions_source_id_normalized_sha256_key',
        'document_versions',
        ['source_id', 'normalized_sha256'],
    )
