from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import pytz
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from loguru import logger
from .models import District, Complaint as ComplaintModel, ActionHistory as ActionHistoryModel, APIRequestTracking
from app.ingestion.schemas import Complaint as ComplaintSchema, ActionHistory as ActionHistorySchema, District as DistrictSchema
from .session import get_db
from app.config import settings
from pydantic import ValidationError

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
        district = get_district_by_id(db, district_data['dist_id'])
        if district:
            # Update existing district
            district.dist_name = district_data['dist_name']
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
def get_complaint_by_ticket(db: Session, ticket_no: str) -> Optional[ComplaintModel]:
    """Get a complaint by its ticket number."""
    return db.query(ComplaintModel).filter(ComplaintModel.ticket_no == ticket_no).first()

def create_or_update_complaint(db: Session, complaint_data: ComplaintSchema) -> ComplaintModel | None: 
    """Create or update a complaint record."""
    
    # Convert Pydantic model to dict for database operations
    complaint_data = complaint_data.model_dump(by_alias=False)
    logger.info(f"Creating or updating complaint: {complaint_data['ticket_no']}")
    try:
        
        complaint = get_complaint_by_ticket(db, complaint_data['ticket_no'])
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
def create_action_history(db: Session, action_data: ActionHistorySchema) -> ActionHistoryModel:
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

def get_action_history_by_ticket(db: Session, ticket_no: str) -> List[ActionHistoryModel]:
    """Get all action history records for a specific complaint."""
    return db.query(ActionHistoryModel).filter(ActionHistoryModel.ticket_no == ticket_no).all()

# Batch operations for ingestion
def batch_create_or_update_districts(db: Session, districts_data: List[DistrictSchema]) -> List[District]:
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

def batch_create_or_update_complaints(db: Session, complaints_data: List[ComplaintSchema]) -> List[ComplaintModel]:
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

def batch_create_action_history(db: Session, actions_data: List[ActionHistorySchema]) -> List[ActionHistoryModel]:
    """Batch create multiple action history records."""
    logger.info(f"Batch creating or updating {len(actions_data)} action history records")

    actions = []
    for action_data in actions_data:
        try:
            action = create_action_history(db, action_data)
            actions.append(action)
        except Exception as e:
            logger.error(f"Error processing action history for ticket {action_data.ticket_no}: {e}")
            continue
    return actions

def bulk_load_districts(db: Session, districts_data: List[DistrictSchema]) -> List[District]:
    """Bulk load districts for fast ingestion."""
    try:
        logger.info(f"Bulk loading {len(districts_data)} districts")
        district_objs = [District(**district.model_dump(by_alias=False)) for district in districts_data]
        db.bulk_save_objects(district_objs, return_defaults=True)
        db.commit()
        return district_objs
    except Exception as e:
        db.rollback()
        logger.error(f"Bulk load districts failed: {e}")
        return batch_create_or_update_districts(db, districts_data)

def bulk_load_complaints(db: Session, complaints_data: List[ComplaintSchema]) -> List[ComplaintModel]:
    """Bulk load complaints for fast ingestion."""
    try:
        logger.info(f"Bulk loading {len(complaints_data)} complaints")
        complaint_objs = [ComplaintModel(**c.model_dump(by_alias=False)) for c in complaints_data]
        db.bulk_save_objects(complaint_objs, return_defaults=True)
        db.commit()
        return complaint_objs
    except Exception as e:
        db.rollback()
        logger.error(f"Bulk load complaints failed: {e}")
        return batch_create_or_update_complaints(db, complaints_data)

def bulk_load_action_histories(db: Session, actions_data: List[ActionHistorySchema]) -> List[ActionHistoryModel]:
    """Bulk load action histories for fast ingestion."""
    try:
        logger.info(f"Bulk loading {len(actions_data)} action histories")
        action_objs = [ActionHistoryModel(**a.model_dump(by_alias=False)) for a in actions_data]
        db.bulk_save_objects(action_objs, return_defaults=True)
        db.commit()
        return action_objs
    except Exception as e:
        db.rollback()
        logger.error(f"Bulk load action histories failed: {e}")
        return batch_create_action_history(db, actions_data)

def record_api_request_success(db: Session, year: int, dist_id: int, status: int, office: int, record_count: int) -> APIRequestTracking:
    """Record a successful API request in db and its results."""
    try:
        tracking = db.query(APIRequestTracking).filter(
            APIRequestTracking.year == year,
            APIRequestTracking.dist_id == dist_id,
            APIRequestTracking.status == status,
            APIRequestTracking.office == office
        ).first()

        if tracking:
            time_zone = pytz.timezone('Asia/Kolkata') # not sure what time zone to use here.
            tracking.last_successful_fetch = datetime.now(time_zone).strftime('%Y-%m-%d %H:%M:%S %Z%z')
            tracking.records_count = record_count
            tracking.failure_count = 0
        else:
            tracking = APIRequestTracking(
                year=year,
                dist_id=dist_id,
                status=status,
                office=office,
                records_count=record_count,
                failure_count=0
            )
            db.add(tracking)

        db.commit()
        db.refresh(tracking)
        return tracking
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error recording API request success: {e}")
        raise

def filter_api_request(db: Session, year: int, dist_id: int, status: int, office: int, days_threshold: int = 7, failure_threshold: int = 3) -> bool:
    """Check if an API request combination was successfully processed or has failed too many times recently."""
    time_zone = pytz.timezone('Asia/Kolkata') # not sure what time zone to use here.
    cutoff_date = datetime.now(time_zone) - timedelta(days=days_threshold)
    
    try:
        tracking = db.query(APIRequestTracking).filter(
            APIRequestTracking.year == year,
            APIRequestTracking.dist_id == dist_id,
            APIRequestTracking.status == status,
            APIRequestTracking.office == office,
            or_(
                APIRequestTracking.last_successful_fetch >= cutoff_date,
                APIRequestTracking.failure_count > failure_threshold
            )
        ).first()
        
        return tracking is not None

    except Exception as e:
        logger.error(f"Error checking if API request was recently processed: {e}")
        return False


def mark_api_request_failed(db: Session, year: int, dist_id: int, status: int, office: int) -> None:
    """Record a failed API request attempt."""
    try:
        tracking = db.query(APIRequestTracking).filter(
            APIRequestTracking.year == year,
            APIRequestTracking.dist_id == dist_id,
            APIRequestTracking.status == status,
            APIRequestTracking.office == office
        ).first()

        if tracking:
            tracking.failure_count += 1
        else:
            tracking = APIRequestTracking(
                year=year,
                dist_id=dist_id,
                status=status,
                office=office,
                failure_count=1
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
        logger.debug(f"District: auto_id: {district.id}, id: {district.dist_id}, name: {district.dist_name}")
