"""Initial migration

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "merchantuser",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_merchantuser_email"), "merchantuser", ["email"], unique=True)

    op.create_table(
        "business",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("logo_url", sa.String(), nullable=True),
        sa.Column("bg_color", sa.String(), nullable=False),
        sa.Column("fg_color", sa.String(), nullable=False),
        sa.Column("label_color", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["merchantuser.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_business_name"), "business", ["name"], unique=False)
    op.create_index(op.f("ix_business_slug"), "business", ["slug"], unique=True)

    op.create_table(
        "rewardprogram",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("stamps_required", sa.Integer(), nullable=False),
        sa.Column("reward_description", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["business.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rewardprogram_business_id"), "rewardprogram", ["business_id"], unique=False)

    op.create_table(
        "customer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("contact", sa.String(), nullable=False),
        sa.Column("contact_type", sa.String(), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(), nullable=False),
        sa.Column("enrollment_channel", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["business.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_customer_business_id"), "customer", ["business_id"], unique=False)

    op.create_table(
        "loyaltycard",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("current_stamps", sa.Integer(), nullable=False),
        sa.Column("rewards_available", sa.Integer(), nullable=False),
        sa.Column("lifetime_stamps", sa.Integer(), nullable=False),
        sa.Column("pass_serial", sa.String(), nullable=False),
        sa.Column("wallet_platform", sa.String(), nullable=False),
        sa.Column("barcode_token", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["business.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.ForeignKeyConstraint(["program_id"], ["rewardprogram.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id", "program_id", name="uq_customer_program"),
    )
    op.create_index(op.f("ix_loyaltycard_barcode_token"), "loyaltycard", ["barcode_token"], unique=True)
    op.create_index(op.f("ix_loyaltycard_business_id"), "loyaltycard", ["business_id"], unique=False)
    op.create_index(op.f("ix_loyaltycard_customer_id"), "loyaltycard", ["customer_id"], unique=False)
    op.create_index(op.f("ix_loyaltycard_pass_serial"), "loyaltycard", ["pass_serial"], unique=True)
    op.create_index(op.f("ix_loyaltycard_program_id"), "loyaltycard", ["program_id"], unique=False)

    op.create_table(
        "scanevent",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("staff_user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["business.id"]),
        sa.ForeignKeyConstraint(["card_id"], ["loyaltycard.id"]),
        sa.ForeignKeyConstraint(["staff_user_id"], ["merchantuser.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scanevent_business_id"), "scanevent", ["business_id"], unique=False)
    op.create_index(op.f("ix_scanevent_card_id"), "scanevent", ["card_id"], unique=False)
    op.create_index(op.f("ix_scanevent_idempotency_key"), "scanevent", ["idempotency_key"], unique=False)
    op.create_index(op.f("ix_scanevent_staff_user_id"), "scanevent", ["staff_user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("scanevent")
    op.drop_table("loyaltycard")
    op.drop_table("customer")
    op.drop_table("rewardprogram")
    op.drop_table("business")
    op.drop_table("merchantuser")
