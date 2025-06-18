import json
import boto3
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session
from .client import JanasunaniAPIClient, JanasunaniAPIError
from .schemas import validate, Complaint, District, ActionHistory, validate_action_history
from ..db.crud import (
    batch_create_or_update_districts,
    batch_create_or_update_complaints,
    batch_create_action_history
)
from ..db.session import get_db
from . import OFFICE, STATUS
from app.config import settings

class IngestionOrchestrator:
    def __init__(self, db: Session):
        self.client = JanasunaniAPIClient()
        self.s3 = boto3.client('s3')
        self.bucket_name = 'grievance-raw-data'
        self.db = db

    def _store_in_s3(self, data: dict, prefix: str):
        """Store raw data in S3 with timestamp."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        key = f"{prefix}/{timestamp}.json"
        
        try:
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=json.dumps(data),
                ContentType='application/json'
            )
            logger.info(f"Successfully stored data in S3: {key}")
        except Exception as e:
            logger.error(f"Error storing data in S3: {e}")
            raise

    def ingest_districts(self):
        """Ingest district data."""
        try:
            districts = self.client.get_districts()
            districts_validated = validate(districts, District, dict_mode=False)
            
            # Store raw data in S3
            if settings.ENV == 'prod':
                self._store_in_s3(districts.model_dump(by_alias=False), 'districts')
            
            # Store processed data in database using CRUD operations
            stored_districts = batch_create_or_update_districts(self.db, districts_validated)
            logger.info(f"Successfully stored {len(stored_districts)} districts in database")
            
            return districts_validated
        except Exception as e:
            logger.error(f"Error ingesting districts: {e}")
            raise

    def ingest_complaints(self, year: int, distId: int, status: int, office: int) -> list[Complaint]:
        """Ingest complaint data."""
        try:
            complaints = self.client.get_complaints(year, distId, status, office)
            complaints_validated = validate(complaints, Complaint, dict_mode=False)
            
            # Store raw data in S3
            if settings.ENV == 'prod':
                self._store_in_s3(complaints, 'complaints')
            
            # Store processed data in database using CRUD operations
            stored_complaints = batch_create_or_update_complaints(self.db, complaints_validated)
            logger.info(f"Successfully stored {len(stored_complaints)} complaints in database")
            
            return complaints_validated
        except Exception as e:
            logger.error(f"Error ingesting complaints: {e}")
            raise

    def ingest_action_history(self, ticket_no: str) -> list[ActionHistory]:
        """Ingest action history data."""
        try:
            action_history = self.client.get_action_history(ticket_no)
            action_history_validated = validate_action_history(action_history)

            # Store raw data in S3
            if settings.ENV == "prod":
                self._store_in_s3(action_history, 'action_history')
            
            # Store processed data in database using CRUD operations
            stored_action_history = batch_create_action_history(self.db, action_history_validated)
            logger.info(f"Successfully stored {len(stored_action_history)} action history in database")

            return action_history_validated
        except Exception as e:
            logger.error(f"Error ingesting action history: {e}")
            raise
            

def lambda_handler(event: dict = None, context: dict = None):
    """AWS Lambda handler function."""
    try:
        db = next(get_db())
        orchestrator = IngestionOrchestrator(db)
        
        # Ingest districts
        districts = orchestrator.ingest_districts()
        
        # Ingest complaints for each district
        for year in range(2021, datetime.now().year ):
            for district in districts:
                for status in STATUS.keys():
                    for office in OFFICE.keys():
                        try:
                            orchestrator.ingest_complaints(
                                year=year,
                                distId=district.dist_id,
                                status=status,
                                office=office
                            )
                        except JanasunaniAPIError as e:
                            continue
        
        return {
            'statusCode': 200,
            'body': json.dumps('Data ingestion completed successfully')
        }
    except Exception as e:
        logger.error(f"Error in lambda handler: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }
        
    finally:
        db.close()
    
if __name__ == "__main__":
    lambda_handler()