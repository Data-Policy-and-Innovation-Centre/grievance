import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pytz
from loguru import logger
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.ingestion.schemas import ActionHistory as ActionHistorySchema
from app.ingestion.schemas import Complaint as ComplaintSchema
from app.ingestion.schemas import District as DistrictSchema

from .models import ActionHistory as ActionHistoryModel
from .models import ActionHistoryAPIRequestTracking, APIRequestTracking
from .models import Complaint as ComplaintModel
from .models import District
from .session import get_db


# District CRUD operations
async def get_district_by_id(db: AsyncSession, dist_id: int) -> Optional[District]:
    """Get a district by its ID."""
    result = await db.execute(select(District).filter(District.dist_id == dist_id))
    return result.scalars().first()


async def get_district_by_name(db: AsyncSession, dist_name: str) -> Optional[District]:
    """Get a district by its name."""
    result = await db.execute(select(District).filter(District.dist_name == dist_name))
    return result.scalars().first()


async def create_or_update_district(
    db: AsyncSession, district_data: DistrictSchema
) -> District:
    """Create or update a district record."""
    # Convert Pydantic model to dict for database operations
    district_data = district_data.model_dump(by_alias=False)

    try:
        logger.info(f"Creating or updating district: {district_data}")
        district = await get_district_by_id(db, district_data["dist_id"])
        if district:
            # Update existing district
            district.dist_name = district_data["dist_name"]
        else:
            # Create new district
            district = District(**district_data)
            db.add(district)

        await db.commit()
        await db.refresh(district)
        return district
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error creating/updating district: {e}")
        raise


async def get_all_districts(db: AsyncSession) -> List[District]:
    """Get all districts."""
    result = await db.execute(select(District))
    return result.scalars().all()


# Complaint CRUD operations
async def get_all_complaints(db: AsyncSession) -> List[ComplaintModel]:
    """Get all complaints."""
    result = await db.execute(select(ComplaintModel))
    return result.scalars().all()


async def get_complaint_by_ticket(db: AsyncSession, ticket_no: str) -> Optional[ComplaintModel]:
    """Get a complaint by its ticket number."""
    result = await db.execute(select(ComplaintModel).filter(ComplaintModel.ticket_no == ticket_no))
    return result.scalars().first()


async def create_or_update_complaint(
    db: AsyncSession, complaint_data: ComplaintSchema
) -> ComplaintModel | None:
    """Create or update a complaint record."""

    # Convert Pydantic model to dict for database operations
    complaint_data = complaint_data.model_dump(by_alias=False)
    logger.info(f"Creating or updating complaint: {complaint_data['ticket_no']}")
    try:

        complaint = await get_complaint_by_ticket(db, complaint_data["ticket_no"])
        if complaint:
            # Update existing complaint
            for key, value in complaint_data.items():
                if hasattr(complaint, key):
                    setattr(complaint, key, value)
        else:
            # Create new complaint
            complaint = ComplaintModel(**complaint_data)
            db.add(complaint)

        await db.commit()
        await db.refresh(complaint)
        return complaint
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"Error creating/updating complaint: {e}")
        raise


async def get_complaints_by_district(db: AsyncSession, district: str) -> List[ComplaintModel]:
    """Get all complaints for a specific district."""
    result = await db.execute(select(ComplaintModel).filter(ComplaintModel.district == district))
    return result.scalars().all()


async def get_complaints_by_status(db: AsyncSession, status: str) -> List[ComplaintModel]:
    """Get all complaints with a specific status."""
    result = await db.execute(select(ComplaintModel).filter(ComplaintModel.status == status))
    return result.scalars().all()


# Action History CRUD operations
async def create_action_history(
    db: AsyncSession, action_data: ActionHistorySchema
) -> ActionHistoryModel:
    """Create a new action history record."""
    try:
        logger.info(f"Creating action history: {action_data.ticket_no}")
        action_data = action_data.model_dump(by_alias=False)
        action = ActionHistoryModel(**action_data)
        db.add(action)
        await db.commit()
        await db.refresh(action)
        return action
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"Error creating action history: {e}")
        raise


async def get_action_history_by_ticket(
    db: AsyncSession, ticket_no: str
) -> List[ActionHistoryModel]:
    """Get all action history records for a specific complaint."""
    result = await db.execute(select(ActionHistoryModel).filter(ActionHistoryModel.ticket_no == ticket_no))
    return result.scalars().all()


# Batch operations for ingestion
async def batch_create_or_update_districts(
    db: AsyncSession, districts_data: List[DistrictSchema]
) -> List[District]:
    """Batch create or update multiple districts."""
    logger.info(f"Batch creating or updating {len(districts_data)} districts")

    districts = []
    for district_data in districts_data:
        try:
            district = await create_or_update_district(db, district_data)
            districts.append(district)
        except Exception as e:
            logger.error(f"Error processing district {district_data.dist_id}: {e}")
            continue
    return districts


async def batch_create_or_update_complaints(
    db: AsyncSession, complaints_data: List[ComplaintSchema]
) -> List[ComplaintModel]:
    """Batch create or update multiple complaints."""
    logger.info(f"Batch creating or updating {len(complaints_data)} complaints")

    complaints = []
    for complaint_data in complaints_data:
        try:
            complaint = await create_or_update_complaint(db, complaint_data)
            complaints.append(complaint)
        except Exception as e:
            logger.error(f"Error processing complaint {complaint_data.ticket_no}: {e}")
            continue
    return complaints


async def batch_create_action_history(
    db: AsyncSession, actions_data: List[ActionHistorySchema]
) -> List[ActionHistoryModel]:
    """Batch create multiple action history records."""
    logger.info(
        f"Batch creating or updating {len(actions_data)} action history records"
    )

    actions = []
    for action_data in actions_data:
        try:
            action = await create_action_history(db, action_data)
            actions.append(action)
        except Exception as e:
            logger.error(
                f"Error processing action history for ticket {action_data.ticket_no}: {e}"
            )
            continue
    return actions


async def bulk_load_districts(
    db: AsyncSession, districts_data: List[DistrictSchema]
) -> List[District]:
    """Bulk load districts for fast ingestion."""
    try:
        logger.info(f"Bulk loading {len(districts_data)} districts")
        existing_dist = {d.dist_id for d in await get_all_districts(db)}
        district_objs = [
            District(**district.model_dump(by_alias=False))
            for district in districts_data
            if district.dist_id not in existing_dist
        ]

        if district_objs:
            db.add_all(district_objs)
            await db.commit()
        else:
            logger.info("No new districts to insert")

        return district_objs
    except Exception as e:
        await db.rollback()
        logger.error(f"Bulk load districts failed: {e}")
        return batch_create_or_update_districts(db, districts_data)


async def bulk_load_complaints(
    db: AsyncSession, complaints_data: List[ComplaintSchema]
) -> List[ComplaintModel]:
    """Bulk load complaints for fast ingestion."""
    try:
        logger.info(f"Bulk loading {len(complaints_data)} complaints")
        query = await db.execute(select(ComplaintModel).filter(
                ComplaintModel.ticket_no.in_([c.ticket_no for c in complaints_data])
            ))
        existing_tickets = {
            c.ticket_no: c
            for c in 
            query.scalars().all()
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
            db.add_all(to_insert)
        if to_update:
            db.add_all(to_update)

        await db.commit()
        logger.info(f"{len(to_insert)} new, {len(to_update)} updated complaints")
        return to_insert + to_update
    except Exception as e:
        await db.rollback()
        logger.error(f"Bulk load complaints failed: {e}")
        return batch_create_or_update_complaints(db, complaints_data)


async def bulk_load_action_histories(
    db: AsyncSession, actions_data: List[ActionHistorySchema]
) -> List[ActionHistoryModel]:
    """Bulk load action histories for fast ingestion."""
    try:
        logger.info(f"Bulk loading {len(actions_data)} action histories")
        existing_actions_map = {
            (a.ticket_no, a.action_taken_date): a
            for a in await get_action_history_by_ticket(db, actions_data[0].ticket_no)
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
            db.add_all(to_insert)
        if to_update:
            db.add_all(to_update)

        await db.commit()
        logger.info(f"{len(to_insert)} new, {len(to_update)} updated action history")
        return to_insert + to_update

    except Exception as e:
        await db.rollback()
        logger.error(f"Bulk load action histories failed: {e}")
        return batch_create_action_history(db, actions_data)


async def update_document_status(
    db: AsyncSession, ticket_no: str, local_path: str, success: bool, error: str = None
):
    import warnings

    warnings.warn(
        "update_document_status is deprecated", DeprecationWarning, stacklevel=2
    )
    complaint = await get_complaint_by_ticket(db, ticket_no=ticket_no)
    time_zone = pytz.timezone("Asia/Kolkata")
    now = datetime.now(time_zone)
    if complaint:
        complaint.local_document_path = local_path
        complaint.document_downloaded = success
        complaint.document_download_date = now
        complaint.document_download_error = error
        await db.commit()
        await db.refresh(complaint)
    return complaint


async def get_complaints_without_documents(
    db: AsyncSession, get_docs_where_errors_occurred: bool = False
) -> list[ComplaintModel]:
    result = await db.execute(select(ComplaintModel).filter(
        ComplaintModel.document_url.isnot(""),
        ComplaintModel.document_url.isnot(None),
        ComplaintModel.document_url.isnot("N/A"),
        ComplaintModel.document_downloaded == False,
        (
            ComplaintModel.document_download_error.isnot(None)
            if get_docs_where_errors_occurred
            else ComplaintModel.document_download_error.is_(None)
            ),
            ))
    return result.scalars().all()


async def get_complaints_with_document_urls(db: AsyncSession) -> list[ComplaintModel]:
    query = await db.execute(select(ComplaintModel).filter(ComplaintModel.document_url.isnot("")))
    return query.scalars().all()


async def record_complaint_api_request_success(
    db: AsyncSession, year: int, dist_id: int, status: int, office: int, record_count: int
) -> Optional[APIRequestTracking]:
    """Record a successful API request in db and its results."""
    try:
        time_zone = pytz.timezone("Asia/Kolkata")
        now = datetime.now(time_zone)
        query = await db.execute(select(APIRequestTracking).filter(
            APIRequestTracking.year == year,
            APIRequestTracking.dist_id == dist_id,
            APIRequestTracking.status == status,
            APIRequestTracking.office == office
        ))
        tracking = query.scalars().first()

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

        await db.commit()
        await db.refresh(tracking)
        return tracking
    except Exception as e:
        await db.rollback()
        logger.error(f"Error recording API request success: {e}")
        raise


async def filter_complaints_api_request(
    db: AsyncSession,
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
        query = await db.execute(select(APIRequestTracking).filter(
            APIRequestTracking.year == year,
            APIRequestTracking.dist_id == dist_id,
            APIRequestTracking.status == status,
            APIRequestTracking.office == office,
        ))
        tracking = query.scalars().first()

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


async def mark_complaints_api_request_failed(
    db: AsyncSession, year: int, dist_id: int, status: int, office: int
) -> Optional[APIRequestTracking]:
    """Record a failed API request attempt."""
    try:
        query = await db.execute(select(APIRequestTracking). filter(
            APIRequestTracking.year == year,
            APIRequestTracking.dist_id == dist_id,
            APIRequestTracking.status == status,
            APIRequestTracking.office == office,
        ))
        tracking = query.scalars().first()

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

        await db.commit()
        await db.refresh(tracking)
        return tracking
    except Exception as e:
        await db.rollback()
        logger.error(f"Error recording API request failure: {e}")
        raise


async def record_action_history_api_request_success(
    db: AsyncSession, ticket_no: str, record_count: int
):
    try:
        time_zone = pytz.timezone("Asia/Kolkata")
        now = datetime.now(time_zone)
        query = await db.execute(select(ActionHistoryAPIRequestTracking).filter(
            ActionHistoryAPIRequestTracking.ticket_no == ticket_no
        ))
        tracking = query.scalars().first() 

        if tracking:
            tracking.last_successful_fetch = now
            tracking.records_count = record_count
            tracking.failure_count = 0
        else:
            tracking = ActionHistoryAPIRequestTracking(
                ticket_no=ticket_no,
                last_successful_fetch=now,
                records_count=record_count,
                failure_count=0,
            )
            db.add(tracking)

        await db.commit()
        await db.refresh(tracking)
        return tracking
    except Exception as e:
        await db.rollback()
        logger.error(f"Error recording action history API request success: {e}")
        raise


async def mark_action_history_api_request_failed(db: AsyncSession, ticket_no: str):
    try:
        query = await db.execute(select(ActionHistoryAPIRequestTracking).filter(
            ActionHistoryAPIRequestTracking.ticket_no == ticket_no
        ))
        tracking = query.scalars().first()

        if tracking:
            tracking.failure_count += 1
        else:
            tracking = ActionHistoryAPIRequestTracking(
                ticket_no=ticket_no, failure_count=1
            )
            db.add(tracking)

        await db.commit()
        await db.refresh(tracking)
        return tracking
    except Exception as e:
        await db.rollback()
        logger.error(f"Error marking action history API request failed: {e}")
        raise


async def get_tickets_needing_action_history(
    db: AsyncSession, days_threshold: int = 7, failure_threshold: int = 3
) -> List[str]:
    """Get ticket numbers that need action history fetching using existing fields."""
    try:
        time_zone = pytz.timezone("Asia/Kolkata")
        cutoff_date = datetime.now(time_zone) - timedelta(days=days_threshold)

        # Get all complaints
        all_complaints = await get_all_complaints(db)
        tickets_needing_fetch = []

        for complaint in all_complaints:
            # Check if this ticket needs action history fetching
            query = await db.execute(select(ActionHistoryAPIRequestTracking).filter(
                ActionHistoryAPIRequestTracking.ticket_no == complaint.ticket_no
            ))
            tracking = query.scalars().first()

            if tracking is None:
                tickets_needing_fetch.append(complaint.ticket_no)
            elif (
                tracking.last_successful_fetch is None
                and tracking.failure_count < failure_threshold
            ):
                tickets_needing_fetch.append(complaint.ticket_no)
            elif (
                tracking.last_successful_fetch is None
                and tracking.failure_count >= failure_threshold
            ):
                continue
            else:
                last_fetch = tracking.last_successful_fetch

                if last_fetch.tzinfo is None:
                    last_fetch = time_zone.localize(last_fetch)

                if (
                    last_fetch < cutoff_date
                    and tracking.failure_count < failure_threshold
                ):
                    tickets_needing_fetch.append(complaint.ticket_no)

        return tickets_needing_fetch
    except Exception as e:
        logger.error(f"Error getting complaints needing action history: {e}")
        return []


async def main():
    from app.ingestion.client import JanasunaniAPIClient, validate

    gen = get_db()
    db = await anext(gen)
    try:
        client = JanasunaniAPIClient()

        districts = client.get_districts()
        districts_validated = validate(districts, DistrictSchema, dict_mode=False)

        data_dist = await bulk_load_districts(db, districts_validated)
        print(data_dist)

    finally:
        await gen.aclose()


if __name__ == "__main__":
    asyncio.run(main())
