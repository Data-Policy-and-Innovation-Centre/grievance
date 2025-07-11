from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pytz
from loguru import logger
from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.schemas import ActionHistory as ActionHistorySchema
from app.ingestion.schemas import Complaint as ComplaintSchema
from app.ingestion.schemas import District as DistrictSchema

from .models import ActionHistory as ActionHistoryModel
from .models import APIRequestTracking
from .models import Complaint as ComplaintModel
from .models import District
from .session import get_db


# District CRUD operations
def get_district_by_id(db: Session, dist_id: int) -> Optional[District]:
    """Get a district by its ID."""
    return db.query(District).filter(District.dist_id == dist_id).first()


def get_district_by_name(db: Session, dist_name: str) -> Optional[District]:
    """Get a district by its name."""
    return db.query(District).filter(District.dist_name == dist_name).first()


def create_or_update_district(db: Session, district_data: DistrictSchema) -> District:
    """Create or update a district record."""
    # Convert Pydantic model to dict for database operations
    district_data = district_data.model_dump(by_alias=False)

    try:
        logger.info(f"Creating or updating district: {district_data}")
        district = get_district_by_id(db, district_data["dist_id"])
        if district:
            # Update existing district
            district.dist_name = district_data["dist_name"]
        else:
            # Create new district
            district = District(**district_data)
            db.add(district)

        db.commit()
        db.refresh(district)
        return district
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error creating/updating district: {e}")
        raise


def get_all_districts(db: Session) -> List[District]:
    """Get all districts."""
    return db.query(District).all()


# Complaint CRUD operations
def get_all_complaints(db: Session) -> List[ComplaintModel]:
    """Get all complaints."""
    return db.query(ComplaintModel).all()


def get_complaint_by_ticket(db: Session, ticket_no: str) -> Optional[ComplaintModel]:
    """Get a complaint by its ticket number."""
    return (
        db.query(ComplaintModel).filter(ComplaintModel.ticket_no == ticket_no).first()
    )


def create_or_update_complaint(
    db: Session, complaint_data: ComplaintSchema
) -> ComplaintModel | None:
    """Create or update a complaint record."""

    # Convert Pydantic model to dict for database operations
    complaint_data = complaint_data.model_dump(by_alias=False)
    logger.info(f"Creating or updating complaint: {complaint_data['ticket_no']}")
    try:

        complaint = get_complaint_by_ticket(db, complaint_data["ticket_no"])
        if complaint:
            # Update existing complaint
            for key, value in complaint_data.items():
                if hasattr(complaint, key):
                    setattr(complaint, key, value)
        else:
            # Create new complaint
            complaint = ComplaintModel(**complaint_data)
            db.add(complaint)

        db.commit()
        db.refresh(complaint)
        return complaint
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error creating/updating complaint: {e}")
        raise


def get_complaints_by_district(db: Session, district: str) -> List[ComplaintModel]:
    """Get all complaints for a specific district."""
    return db.query(ComplaintModel).filter(ComplaintModel.district == district).all()


def get_complaints_by_status(db: Session, status: str) -> List[ComplaintModel]:
    """Get all complaints with a specific status."""
    return db.query(ComplaintModel).filter(ComplaintModel.status == status).all()


# Action History CRUD operations
def create_action_history(
    db: Session, action_data: ActionHistorySchema
) -> ActionHistoryModel:
    """Create a new action history record."""
    try:
        logger.info(f"Creating action history: {action_data.ticket_no}")
        action_data = action_data.model_dump(by_alias=False)
        action = ActionHistoryModel(**action_data)
        db.add(action)
        db.commit()
        db.refresh(action)
        return action
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error creating action history: {e}")
        raise


def get_action_history_by_ticket(
    db: Session, ticket_no: str
) -> List[ActionHistoryModel]:
    """Get all action history records for a specific complaint."""
    return (
        db.query(ActionHistoryModel)
        .filter(ActionHistoryModel.ticket_no == ticket_no)
        .all()
    )


# Batch operations for ingestion
def batch_create_or_update_districts(
    db: Session, districts_data: List[DistrictSchema]
) -> List[District]:
    """Batch create or update multiple districts."""
    logger.info(f"Batch creating or updating {len(districts_data)} districts")

    districts = []
    for district_data in districts_data:
        try:
            district = create_or_update_district(db, district_data)
            districts.append(district)
        except Exception as e:
            logger.error(f"Error processing district {district_data.dist_id}: {e}")
            continue
    return districts


def batch_create_or_update_complaints(
    db: Session, complaints_data: List[ComplaintSchema]
) -> List[ComplaintModel]:
    """Batch create or update multiple complaints."""
    logger.info(f"Batch creating or updating {len(complaints_data)} complaints")

    complaints = []
    for complaint_data in complaints_data:
        try:
            complaint = create_or_update_complaint(db, complaint_data)
            complaints.append(complaint)
        except Exception as e:
            logger.error(f"Error processing complaint {complaint_data.ticket_no}: {e}")
            continue
    return complaints


def batch_create_action_history(
    db: Session, actions_data: List[ActionHistorySchema]
) -> List[ActionHistoryModel]:
    """Batch create multiple action history records."""
    logger.info(
        f"Batch creating or updating {len(actions_data)} action history records"
    )

    actions = []
    for action_data in actions_data:
        try:
            action = create_action_history(db, action_data)
            actions.append(action)
        except Exception as e:
            logger.error(
                f"Error processing action history for ticket {action_data.ticket_no}: {e}"
            )
            continue
    return actions


def bulk_load_districts(
    db: Session, districts_data: List[DistrictSchema]
) -> List[District]:
    """Bulk load districts for fast ingestion."""
    try:
        logger.info(f"Bulk loading {len(districts_data)} districts")
        existing_dist = {d.dist_id for d in get_all_districts(db)}
        district_objs = [
            District(**district.model_dump(by_alias=False))
            for district in districts_data
            if district.dist_id not in existing_dist
        ]

        if district_objs:
            db.bulk_save_objects(district_objs, return_defaults=True)
            db.commit()
        else:
            logger.info("No new districts to insert")

        return district_objs
    except Exception as e:
        db.rollback()
        logger.error(f"Bulk load districts failed: {e}")
        return batch_create_or_update_districts(db, districts_data)


def bulk_load_complaints(
    db: Session, complaints_data: List[ComplaintSchema]
) -> List[ComplaintModel]:
    """Bulk load complaints for fast ingestion."""
    try:
        logger.info(f"Bulk loading {len(complaints_data)} complaints")
        existing_tickets = {
            c.ticket_no: c
            for c in db.query(ComplaintModel)
            .filter(
                ComplaintModel.ticket_no.in_([c.ticket_no for c in complaints_data])
            )
            .all()
        }
        to_insert = []
        to_update = []

        for c in complaints_data:
            c_dict = c.model_dump(by_alias=False)
            existing_obj = existing_tickets.get(c.ticket_no)

            if existing_obj is None:
                to_insert.append(ComplaintModel(**c_dict))
            else:
                updated = False
                for field, value in c_dict.items():
                    if getattr(existing_obj, field) != value:
                        setattr(existing_obj, field, value)
                        updated = True
                if updated:
                    to_update.append(existing_obj)

        if to_insert:
            db.bulk_save_objects(to_insert, return_defaults=True)
        if to_update:
            db.add_all(to_update)

        db.commit()
        logger.info(f"{len(to_insert)} new, {len(to_update)} updated complaints")
        return to_insert + to_update
    except Exception as e:
        db.rollback()
        logger.error(f"Bulk load complaints failed: {e}")
        return batch_create_or_update_complaints(db, complaints_data)


def bulk_load_action_histories(
    db: Session, actions_data: List[ActionHistorySchema]
) -> List[ActionHistoryModel]:
    """Bulk load action histories for fast ingestion."""
    try:
        logger.info(f"Bulk loading {len(actions_data)} action histories")

        existing_actions_map = {
            (a.ticket_no, a.action_taken_date): a
            for a in get_action_history_by_ticket(db, actions_data[0].ticket_no)
        }

        to_insert = []
        to_update = []

        for action in actions_data:
            a_dict = action.model_dump(by_alias=False)
            key = (action.ticket_no, action.action_taken_date)
            exist_action = existing_actions_map.get(key)

            if exist_action is None:
                to_insert.append(ActionHistoryModel(**a_dict))
            else:
                updated = False
                for field, value in a_dict.items():
                    if getattr(exist_action, field) != value:
                        setattr(exist_action, field, value)
                        updated = True
                if updated:
                    to_update.append(exist_action)

        if to_insert:
            db.bulk_save_objects(to_insert, return_defaults=True)
        if to_update:
            db.add_all(to_update)

        db.commit()
        logger.info(f"{len(to_insert)} new, {len(to_update)} updated action history")
        return to_insert + to_update

    except Exception as e:
        db.rollback()
        logger.error(f"Bulk load action histories failed: {e}")
        return batch_create_action_history(db, actions_data)


def update_document_status(
    db: Session, ticket_no: str, local_path: str, success: bool, error: str = None
):
    complaint = get_complaint_by_ticket(db, ticket_no=ticket_no)
    if complaint:
        complaint.local_document_path = local_path
        complaint.document_downloaded = success
        complaint.document_download_date = datetime.now()
        complaint.document_download_error = error
        db.commit()
        db.refresh(complaint)
    return complaint


def get_complaints_without_documents(db: Session) -> list[ComplaintModel]:
    return (
        db.query(ComplaintModel)
        .filter(
            ComplaintModel.document_url.isnot(None),
            ComplaintModel.document_downloaded == False,
        )
        .all()
    )


def get_complaints_with_document_urls(db: Session) -> list[ComplaintModel]:
    return (
        db.query(ComplaintModel).filter(ComplaintModel.document_url.isnot(None)).all()
    )


def record_api_request_success(
    db: Session, year: int, dist_id: int, status: int, office: int, record_count: int
) -> APIRequestTracking:
    """Record a successful API request in db and its results."""
    try:
        time_zone = pytz.timezone("Asia/Kolkata")
        now = datetime.now(time_zone)
        tracking = (
            db.query(APIRequestTracking)
            .filter(
                APIRequestTracking.year == year,
                APIRequestTracking.dist_id == dist_id,
                APIRequestTracking.status == status,
                APIRequestTracking.office == office,
            )
            .first()
        )

        if tracking:
            # time_zone = pytz.timezone('Asia/Kolkata') # not sure what time zone to use here.
            tracking.last_successful_fetch = now
            tracking.records_count = record_count
            tracking.failure_count = 0
        else:
            tracking = APIRequestTracking(
                year=year,
                dist_id=dist_id,
                status=status,
                office=office,
                records_count=record_count,
                last_successful_fetch=now,
                failure_count=0,
            )
            db.add(tracking)

        db.commit()
        db.refresh(tracking)
        return tracking
    except Exception as e:
        db.rollback()
        logger.error(f"Error recording API request success: {e}")
        raise


def filter_api_request(
    db: Session,
    year: int,
    dist_id: int,
    status: int,
    office: int,
    days_threshold: int = 7,
    failure_threshold: int = 3,
) -> bool:
    """Check if an API request combination was successfully processed or has failed too many times recently."""
    time_zone = pytz.timezone("Asia/Kolkata")
    cutoff_date = datetime.now(time_zone) - timedelta(days=days_threshold)

    try:
        tracking = (
            db.query(APIRequestTracking)
            .filter(
                APIRequestTracking.year == year,
                APIRequestTracking.dist_id == dist_id,
                APIRequestTracking.status == status,
                APIRequestTracking.office == office,
            )
            .first()
        )

        if tracking is None:
            return False

        # Only check last_successful_fetch if it is not None
        recent_success = False
        if tracking.last_successful_fetch is not None:
            if tracking.last_successful_fetch.tzinfo is None:
                tracking.last_successful_fetch = time_zone.localize(
                    tracking.last_successful_fetch
                )
            recent_success = tracking.last_successful_fetch >= cutoff_date

        return recent_success or tracking.failure_count >= failure_threshold
    except Exception as e:
        logger.error(f"Error checking if API request was recently processed: {e}")
        return False


def mark_api_request_failed(
    db: Session, year: int, dist_id: int, status: int, office: int
) -> None:
    """Record a failed API request attempt."""
    try:
        tracking = (
            db.query(APIRequestTracking)
            .filter(
                APIRequestTracking.year == year,
                APIRequestTracking.dist_id == dist_id,
                APIRequestTracking.status == status,
                APIRequestTracking.office == office,
            )
            .first()
        )

        if tracking:
            tracking.failure_count += 1
        else:
            tracking = APIRequestTracking(
                year=year,
                dist_id=dist_id,
                status=status,
                office=office,
                failure_count=1,
            )
            db.add(tracking)

        db.commit()
        db.refresh(tracking)
        return tracking
    except Exception as e:
        db.rollback()
        logger.error(f"Error recording API request failure: {e}")
        raise


if __name__ == "__main__":
    db = next(get_db())
    districts = get_all_districts(db)
    for district in districts:
        logger.debug(
            f"District: auto_id: {district.id}, id: {district.dist_id}, name: {district.dist_name}"
        )
