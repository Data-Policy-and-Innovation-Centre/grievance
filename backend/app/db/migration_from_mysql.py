from sqlalchemy import MetaData, Table, select, func, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from loguru import logger
from more_itertools import chunked

from app.db.models import Base, Complaint as ComplaintModel, ActionHistory as ActionHistoryModel
from app.ingestion.schemas import Complaint as ComplaintSchema, ActionHistory as ActionHistorySchema, validate, validate_action_history
from app.config import directories

MYSQL_URL   = "mysql+pymysql://myapp:dpic@127.0.0.1:3306/myapp_db"
SQLITE_PATH = directories.PROCESSED_DATA / "myapp.db"
CHUNK_SIZE  = 1000

def setup_engines():
    # enable pre‐ping so stale connections auto‐reconnect
    mysql_engine  = create_engine(MYSQL_URL, pool_pre_ping=True, pool_recycle=3600)
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    sqlite_engine = create_engine(f"sqlite:///{SQLITE_PATH}")
    return mysql_engine, sqlite_engine

def ensure_sqlite_schema(sqlite_engine):
    # create tables if they don't exist, but don't delete data
    Base.metadata.create_all(bind=sqlite_engine)

def get_existing_ticket_no(sqlite_sess):
    return set(
        sqlite_sess.scalars(
            select(ComplaintModel.ticket_no)
        ).all()
    )

def reset_sqlite(sqlite_engine):
    if SQLITE_PATH.exists():
        SQLITE_PATH.unlink()
    Base.metadata.create_all(bind=sqlite_engine)

def migrate_complaints(mysql_sess, sqlite_sess):
    table_name, Schema, Model = (
        "t_janasunani_etl_pre_data",
        ComplaintSchema,
        ComplaintModel,
    )
    meta        = MetaData()
    complaint_t = Table(table_name, meta, autoload_with=mysql_sess.bind)

    # Count total rows up front
    total = mysql_sess.execute(
        select(func.count()).select_from(complaint_t)
    ).scalar_one()
    logger.info(f"Starting complaints migration ({total} rows)")

    offset, batch_no = 0, 0
    while offset < total:
        rows = mysql_sess.execute(
            select(complaint_t).limit(CHUNK_SIZE).offset(offset)
        ).mappings().all()
        if not rows:
            break

        logger.info(f"Complaint batch {batch_no} (rows {offset}–{offset + len(rows)})")
        validated = [Schema(**r).model_dump(by_alias=False) for r in rows]

        try:
            sqlite_sess.bulk_insert_mappings(Model, validated)
            sqlite_sess.commit()
        except IntegrityError:
            sqlite_sess.rollback()
            for rec in validated:
                try:
                    sqlite_sess.bulk_insert_mappings(Model, [rec])
                    sqlite_sess.commit()
                except IntegrityError:
                    sqlite_sess.rollback()
                    logger.warning(f"Skipping bad complaint {rec.get('ticket_no')}")

        offset  += CHUNK_SIZE
        batch_no += 1

    # build and return tracking map
    rows = sqlite_sess.execute(
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

def main():
    mysql_engine, sqlite_engine = setup_engines()
    MySQLSession  = sessionmaker(bind=mysql_engine)
    SQLiteSession = sessionmaker(bind=sqlite_engine)

    reset_sqlite(sqlite_engine)

    mysql_sess  = MySQLSession()
    sqlite_sess = SQLiteSession()

    tracking_map = migrate_complaints(mysql_sess, sqlite_sess)
    migrate_action_history(mysql_sess, sqlite_sess, tracking_map)

    mysql_sess.close()
    sqlite_sess.close()
    logger.info(f"✅ Export completed into {SQLITE_PATH}")

if __name__ == "__main__":
    main()