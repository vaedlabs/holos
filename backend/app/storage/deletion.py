"""Deleting an account (Plan C.18) and retrying image deletions that failed (C.19).

    await delete_account(engine, user_id, store)   # rows now, images after commit
    await retry_deletions(engine, store)           # the 2-minute job (P4.11)

One transaction deletes the user, whose rows cascade (C.11 †), and every row keyed by
the account's principal key, which has no foreign key: leases, crisis flag, rate
counters, spend. After the commit the images go: the account's `users/{id}/` prefix
and any image from before P4.9 (`images/{id}_….jpg`). An image delete that fails adds a
`deletion_queue` row, so the account is gone at once and its images soon after.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.storage.images import ImageStore, user_prefix

log = logging.getLogger(__name__)

MAX_ERROR = 500


async def delete_account(engine: AsyncEngine, user_id: int, store: ImageStore) -> None:
    key = f"user:{user_id}"
    async with engine.begin() as conn:
        old = (await conn.execute(text(
            "SELECT image_path FROM conversation_messages WHERE user_id = :u "
            "AND image_path IS NOT NULL AND image_path NOT LIKE 'users/%'"),
            {"u": user_id})).scalars().all()
        for table, column in (("inflight_leases", "principal_key"),
                              ("principal_flags", "principal_key"),
                              ("chat_requests", "principal_key")):
            await conn.execute(text(f"DELETE FROM {table} WHERE {column} = :k"), {"k": key})
        for table in ("rate_counters", "spend"):  # "user:7" and "user:7:minute", not "user:70"
            await conn.execute(text(
                f"DELETE FROM {table} WHERE key = :k OR starts_with(key, :p)"),
                {"k": key, "p": f"{key}:"})
        await conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
    for prefix in [user_prefix(user_id), *sorted(set(old))]:
        await delete_or_queue(engine, store, prefix)


async def delete_or_queue(engine: AsyncEngine, store: ImageStore, prefix: str) -> None:
    try:
        await store.delete_prefix(prefix)
    except Exception as error:  # any storage failure: the job retries it
        log.warning("image delete failed, queued: %s", type(error).__name__)
        async with engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO deletion_queue (prefix, attempts, last_error) "
                "VALUES (:p, 1, :e)"), {"p": prefix, "e": repr(error)[:MAX_ERROR]})


async def retry_deletions(engine: AsyncEngine, store: ImageStore, limit: int = 100) -> int:
    """Each queued prefix once; done ones leave the queue. Returns how many are done."""
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT id, prefix FROM deletion_queue ORDER BY id LIMIT :n"),
            {"n": limit})).all()
    done = 0
    for row in rows:
        try:
            await store.delete_prefix(row.prefix)
        except Exception as error:
            async with engine.begin() as conn:
                await conn.execute(text(
                    "UPDATE deletion_queue SET attempts = attempts + 1, last_error = :e "
                    "WHERE id = :i"), {"e": repr(error)[:MAX_ERROR], "i": row.id})
            continue
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM deletion_queue WHERE id = :i"), {"i": row.id})
        done += 1
    return done
