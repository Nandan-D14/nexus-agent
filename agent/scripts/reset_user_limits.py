# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Script to reset usage limits for all users in Firestore."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

from nexus.config import settings
from nexus.firebase import get_firestore_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reset_user_limits")


def reset_all_users(*, dry_run: bool = False) -> int:
    """Reset credit and token usage for all user accounts in Firestore."""
    db = get_firestore_client()
    users_ref = db.collection("users")
    docs = list(users_ref.stream())

    total = len(docs)
    logger.info("Found %d user document(s) in Firestore.", total)

    if total == 0:
        logger.info("No user documents found.")
        return 0

    now = datetime.now(timezone.utc)
    reset_payload = {
        "creditUsage": 0,
        "creditLimit": settings.default_credit_limit,
        "creditResetVersion": settings.default_credit_reset_version,
        "creditResetAt": now,
        "tokenUsage": 0,
        "tokenLimit": settings.default_token_limit,
        "planId": settings.default_plan_id,
        "planName": settings.default_plan_name,
        "planPriceUsd": settings.default_plan_price_usd,
        "planStatus": "active",
        "billingMode": "internal_entitlement",
        "creditUnitUsd": settings.default_credit_unit_usd,
        "updatedAt": now,
    }

    if dry_run:
        logger.info(
            "[DRY RUN] Would update %d user(s) with reset version '%s' and credit limit %d.",
            total,
            settings.default_credit_reset_version,
            settings.default_credit_limit,
        )
        return total

    batch = db.batch()
    batch_count = 0
    updated_count = 0

    for doc in docs:
        batch.update(doc.reference, reset_payload)
        batch_count += 1
        updated_count += 1

        # Firestore allows up to 500 operations per batch
        if batch_count == 500:
            batch.commit()
            logger.info("Committed batch of 500 users (%d/%d)...", updated_count, total)
            batch = db.batch()
            batch_count = 0

    if batch_count > 0:
        batch.commit()
        logger.info("Committed final batch of %d users.", batch_count)

    logger.info("Successfully reset limits for all %d user(s).", updated_count)
    return updated_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset credit & token usage limits for all users.")
    parser.add_argument("--dry-run", action="store_true", help="Preview the count without making updates.")
    args = parser.parse_args()

    reset_all_users(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
