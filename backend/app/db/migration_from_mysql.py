import asyncio
from typing import Dict, Optional, Tuple

from loguru import logger
from more_itertools import chunked
from pydantic import ValidationError
from sqlalchemy import Engine, MetaData, Table, create_engine, distinct, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import directories
from app.db.models import ActionHistory as ActionHistoryModel
from app.db.models import Base
from app.db.models import Complaint as ComplaintModel
from app.ingestion.schemas import ActionHistory as ActionHistorySchema
from app.ingestion.schemas import Complaint as ComplaintSchema

MYSQL_URL = "mysql+pymysql://myapp:dpic@127.0.0.1:3306/myapp_db"
SQLITE_PATH = directories.RAW_DATA / "grievance.db"
CHUNK_SIZE = 1000


def setup_engines() -> Tuple[Engine, AsyncEngine]:
    # enable pre‐ping so stale connections auto‐reconnect
    mysql_engine = create_engine(MYSQL_URL, pool_pre_ping=True, pool_recycle=3600)
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    sqlite_engine = create_async_engine(f"sqlite+aiosqlite:///{SQLITE_PATH}")
    return mysql_engine, sqlite_engine


async def init_db(sqlite_engine: AsyncEngine) -> None:
    """Initialize the database and create tables."""
    async with sqlite_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db(AsyncSessionLocal: sessionmaker):
    """Get a database session."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_existing_ticket_no(db: AsyncSession):
    result = await db.execute(select(ComplaintModel.ticket_no).distinct())
    return result.scalars().all()


async def get_existing_trackingId(db: AsyncSession):
    result = await db.execute(select(ActionHistoryModel.trackingId).distinct())
    return result.scalars().all()


async def migrate_complaints(
    mysql_sess: Session, sqlite_sess: AsyncSession
) -> Optional[Dict[str, str]]:
    meta = MetaData()
    complaint_t = Table(
        "t_janasunani_etl_pre_data", meta, autoload_with=mysql_sess.bind
    )

    # Getting all ticket numbers from MySQL database
    def fetch_mysql_tickets():
        query = select(distinct(complaint_t.c.ticketNumber))
        return set(mysql_sess.execute(query).scalars().all())

    async def build_tracking_map() -> Dict[str, str]:
        res = await sqlite_sess.execute(
            select(ComplaintModel.trackingId, ComplaintModel.ticket_no)
        )
        rows = res.all()
        tracking_map = dict(rows)
        logger.info(f"Migrated {len(tracking_map)} complaints")
        return tracking_map

    ticket_nos = await asyncio.to_thread(fetch_mysql_tickets)

    # Getting the ticket numbers already at the SQLite database
    complaints_in_db = set(await get_existing_ticket_no(sqlite_sess))

    # Getting the remaining ticket numbers to insert
    pending_tickets = ticket_nos.difference(complaints_in_db)

    total = len(pending_tickets)
    if total == 0:
        logger.success("All complaints already migrated")
        return await build_tracking_map()

    logger.info(f"Starting complaints migration ({total} rows)")

    batch_no = 0
    for chunk in chunked(pending_tickets, CHUNK_SIZE):

        def fetch_chunk(chunk=chunk):
            stmt = select(complaint_t).where(complaint_t.c.ticketNumber.in_(chunk))
            return mysql_sess.execute(stmt).mappings().all()

        results: list[dict] = await asyncio.to_thread(fetch_chunk)
        logger.info(f"Complaint batch {batch_no}")

        validated = [ComplaintSchema(**r).model_dump(by_alias=False) for r in results]
        to_insert = [ComplaintModel(**c) for c in validated]

        try:
            sqlite_sess.add_all(to_insert)
            await sqlite_sess.commit()
            logger.info(f"Batch {batch_no} inserted {len(to_insert)} rows")
        except IntegrityError:
            await sqlite_sess.rollback()
            for c in validated:
                try:
                    sqlite_sess.add(ComplaintModel(**c))
                    await sqlite_sess.commit()
                except IntegrityError:
                    await sqlite_sess.rollback()
                    logger.warning(f"Skipping duplicated {c['ticket_no']}")
        batch_no += 1

    # build and return tracking map
    return await build_tracking_map()


async def migrate_action_history(
    mysql_sess: Session, sqlite_sess: AsyncSession, tracking_map: Dict[str, str]
):
    if not tracking_map:
        logger.info("No action_history to migrate (empty tracking_map).")
        return

    table_name, Schema, Model = (
        "t_janasunani_etl_history_pre_data",
        ActionHistorySchema,
        ActionHistoryModel,
    )
    meta = MetaData()
    history_t = Table(table_name, meta, autoload_with=mysql_sess.bind)

    total = mysql_sess.execute(
        select(func.count())
        .select_from(history_t)
        .where(history_t.c.trackingId.in_(tracking_map.keys()))
    ).scalar_one()

    logger.info(f"Starting action_history migration ({total} rows)")

    offset = 0
    batch_no = 0
    inserted = 0

    while offset < total:
        rows = (
            mysql_sess.execute(
                select(history_t)
                .where(history_t.c.trackingId.in_(tracking_map.keys()))
                .limit(CHUNK_SIZE)
                .offset(offset)
            )
            .mappings()
            .all()
        )

        if not rows:
            break

        logger.info(f"History batch {batch_no} (rows {offset}–{offset + len(rows)})")

        to_insert = []
        for r in rows:
            r = dict(r)
            r["ticketNumber"] = tracking_map.get(r["trackingId"])
            try:
                rec = Schema(**r).model_dump(by_alias=False)
            except ValidationError as e:
                logger.error(f"Validation error for {r['trackingId']}: {e}")
                continue
            to_insert.append(rec)

        # Prefer ON CONFLICT DO NOTHING when you can (requires a unique constraint/index)
        stmt = sqlite_insert(Model).values(to_insert)
        stmt = (
            stmt.on_conflict_do_nothing(
                index_elements=["trackingId", "action_taken_date"]
            )
            if hasattr(stmt, "on_conflict_do_nothing")
            else stmt
        )

        try:
            await sqlite_sess.execute(stmt)
            await sqlite_sess.commit()
            inserted += len(to_insert)
        except (IntegrityError, OperationalError):
            await sqlite_sess.rollback()
            # per-row fallback
            for rec in to_insert:
                try:
                    one_stmt = sqlite_insert(Model).values(rec)
                    if hasattr(one_stmt, "on_conflict_do_nothing"):
                        one_stmt = one_stmt.on_conflict_do_nothing()
                    await sqlite_sess.execute(one_stmt)
                    await sqlite_sess.commit()
                    inserted += 1
                except (IntegrityError, OperationalError):
                    await sqlite_sess.rollback()
                    logger.warning(
                        f"Skipping bad history record for trackingId {rec.get('trackingId')}"
                    )

        offset += CHUNK_SIZE
        batch_no += 1

    logger.info(f"Inserted {inserted}/{total} action_history records")


async def main():
    logger.info("Starting migration")

    mysql_engine, sqlite_engine = setup_engines()
    try:
        await init_db(sqlite_engine)

        MySQLSession = sessionmaker(bind=mysql_engine, expire_on_commit=False)
        SQLiteSession = sessionmaker(
            bind=sqlite_engine, class_=AsyncSession, expire_on_commit=False
        )

        with MySQLSession() as mysql_sess:
            async with SQLiteSession() as sqlite_sess:
                tracking_map = await migrate_complaints(mysql_sess, sqlite_sess)
                await migrate_action_history(mysql_sess, sqlite_sess, tracking_map)

        logger.info(f"Export completed into {SQLITE_PATH}")

    finally:
        try:
            mysql_engine.dispose()
        except Exception:
            pass
        try:
            await sqlite_engine.dispose()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
