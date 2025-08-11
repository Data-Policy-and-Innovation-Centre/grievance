import asyncio
from sqlalchemy import MetaData, Table, select, func, create_engine, distinct, Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
from loguru import logger
from more_itertools import chunked
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine
from app.db.session import get_db
from typing import Tuple, Dict, Optional

from app.db.models import Base, Complaint as ComplaintModel, ActionHistory as ActionHistoryModel
from app.ingestion.schemas import Complaint as ComplaintSchema, ActionHistory as ActionHistorySchema, validate, validate_action_history
from app.config import directories

MYSQL_URL   = "mysql+pymysql://myapp:dpic@127.0.0.1:3306/myapp_db"
SQLITE_PATH = directories.PROCESSED_DATA / "myapp.db"
CHUNK_SIZE  = 1000

def setup_engines() -> Tuple[Engine, AsyncEngine]:
    # enable pre‐ping so stale connections auto‐reconnect
    mysql_engine  = create_engine(MYSQL_URL, pool_pre_ping=True, pool_recycle=3600)
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

async def migrate_complaints(mysql_sess: Engine, sqlite_sess: AsyncEngine) -> Optional[Dict[str, str]]:
    meta        = MetaData()
    complaint_t = Table('t_janasunani_etl_pre_data', meta, autoload_with=mysql_sess.bind)

    # Getting all ticket numbers from MySQL database
    def fetch_mysql_tickets():
        query = select(distinct(complaint_t.c.ticketNumber))
        return set(mysql_sess.execute(query).scalars().all())

    ticket_nos = await asyncio.to_thread(fetch_mysql_tickets)

    # Getting the ticket numbers already at the SQLite database
    complaints_in_db = set(await get_existing_ticket_no(sqlite_sess))

    # Getting the remaining ticket numbers to insert
    pending_tickets = ticket_nos.difference(complaints_in_db)

    total = len(pending_tickets)
    if total == 0:
        logger.success(f"All complaints already migrated")
        return None
    
    logger.info(f"Starting complaints migration ({total} rows)")

    tracking_map: dict[str,str] = {}
    batch_no = 0
    for chunk in chunked(pending_tickets, CHUNK_SIZE):
        def fetch_chunk():
            stmt = select(complaint_t).where(complaint_t.c.ticketNumber.in_(chunk))
            return mysql_sess.execute(stmt).mappings().all()

        results: list[dict] = await asyncio.to_thread(fetch_chunk)

        logger.info(f"Complaint batch {batch_no}")
        validated = [ComplaintSchema(**r).model_dump(by_alias=False) for r in results]

        to_insert = [ComplaintModel(**complaint) for complaint in validated]
        try: 
            sqlite_sess.add_all(to_insert)
            await sqlite_sess.commit()
            logger.info(f"Batch {batch_no} inserted {len(to_insert)} rows")
        except IntegrityError:
            await sqlite_sess.rollback()
            for complaint in validated:
                try:
                    complaint_data = ComplaintModel(**complaint)
                    sqlite_sess.add(complaint_data)
                    await sqlite_sess.commit()
                except IntegrityError:
                    await sqlite_sess.rollback()
                    logger.warning(f"Skipping duplicated {complaint['ticket_no']}")

        batch_no += 1

    # build and return tracking map
    rows = await sqlite_sess.execute(
        select(ComplaintModel.trackingId, ComplaintModel.ticket_no)
    ).all()
    tracking_map = {tid: tn for tid, tn in rows}
    logger.info(f"Migrated {len(tracking_map)} complaints")
    return tracking_map

def migrate_action_history(mysql_sess, sqlite_sess, tracking_map):
    table_name, Schema, Model = (
        "t_janasunani_etl_history_pre_data",
        ActionHistorySchema,
        ActionHistoryModel,
    )
    meta  = MetaData()
    history_t = Table(table_name, meta, autoload_with=mysql_sess.bind)

    # Count only relevant rows
    total = mysql_sess.execute(
        select(func.count()).select_from(history_t)
        .where(history_t.c.trackingId.in_(tracking_map.keys()))
    ).scalar_one()
    logger.info(f"Starting action_history migration ({total} rows)")

    offset, batch_no, inserted = 0, 0, 0
    while offset < total:
        rows = mysql_sess.execute(
            select(history_t)
            .where(history_t.c.trackingId.in_(tracking_map.keys()))
            .limit(CHUNK_SIZE)
            .offset(offset)
        ).mappings().all()
        if not rows:
            break

        logger.info(f"History batch {batch_no} (rows {offset}–{offset + len(rows)})")
        to_insert = []
        for r in rows:
            rec = Schema(**r).model_dump(by_alias=False)
            rec["ticket_no"] = tracking_map.get(rec["trackingId"])
            to_insert.append(rec)

        try:
            sqlite_sess.bulk_insert_mappings(Model, to_insert)
            sqlite_sess.commit()
            inserted += len(to_insert)
        except IntegrityError:
            sqlite_sess.rollback()
            for rec in to_insert:
                try:
                    sqlite_sess.bulk_insert_mappings(Model, [rec])
                    sqlite_sess.commit()
                    inserted += 1
                except IntegrityError:
                    sqlite_sess.rollback()
                    logger.warning(f"Skipping bad history record for trackingId {rec.get('trackingId')}")

        offset    += CHUNK_SIZE
        batch_no  += 1

    logger.info(f"Inserted {inserted}/{total} action_history records")

async def main():
    logger.info(f"Starting migration")

    try:
        mysql_engine, sqlite_engine = setup_engines()
        MySQLSession  = sessionmaker(bind=mysql_engine)
        SQLiteSession = sessionmaker(expire_on_commit=False, bind = sqlite_engine, class_=AsyncSession)

        mysql_sess  = MySQLSession()
        gen = get_db(SQLiteSession)
        sqlite_sess = await anext(gen)

        tracking_map = await migrate_complaints(mysql_sess, sqlite_sess)
        migrate_action_history(mysql_sess, sqlite_sess, tracking_map)

        mysql_sess.close()

    finally:
        if "sqlite_sess" in locals():
            await gen.aclose()

    logger.info(f"Export completed into {SQLITE_PATH}")

if __name__ == "__main__":
    asyncio.run(main())