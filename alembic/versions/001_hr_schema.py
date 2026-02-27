"""Create hr schema employees table from production schema

Revision ID: 001_hr_schema
Revises:
Create Date: 2026-02-27

NOTE: Current production uses public.employees (no schema prefix).
This migration creates hr.employees on loomi-db for Phase 1 cutover.
The public.employees table is preserved during the 2-week hold period.
Also creates eid_seq in the hr schema (mirrors public.eid_seq).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_hr_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS hr")
    op.execute("CREATE SEQUENCE IF NOT EXISTS hr.eid_seq START 1")
    op.create_table(
        "employees",
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("nationality", sa.Text(), nullable=True),
        sa.Column("date_of_birth", sa.Text(), nullable=True),
        sa.Column("passport_number", sa.Text(), nullable=True),
        sa.Column("job_title", sa.Text(), nullable=True),
        sa.Column("base_salary", sa.Numeric(), nullable=True),
        sa.Column("total_salary", sa.Numeric(), nullable=True),
        sa.Column("contract_start_date", sa.Text(), nullable=True),
        sa.Column("contract_expiry_date", sa.Text(), nullable=True),
        sa.Column("insurance_status", sa.Text(), nullable=True),
        sa.Column("mohre_transaction_no", sa.Text(), nullable=True),
        sa.Column("source_file", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Numeric(), nullable=True),
        sa.Column("field_scores", postgresql.JSONB(), nullable=True),
        sa.Column("source_doc_type", sa.Text(), nullable=True),
        sa.Column("ingested_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("employee_id"),
        schema="hr",
    )
    op.create_index("ix_hr_employees_passport", "employees", ["passport_number"], unique=True, schema="hr")
    op.create_index("ix_hr_employees_mohre", "employees", ["mohre_transaction_no"], unique=True, schema="hr")


def downgrade() -> None:
    op.drop_index("ix_hr_employees_mohre", table_name="employees", schema="hr")
    op.drop_index("ix_hr_employees_passport", table_name="employees", schema="hr")
    op.drop_table("employees", schema="hr")
    op.execute("DROP SEQUENCE IF EXISTS hr.eid_seq")
