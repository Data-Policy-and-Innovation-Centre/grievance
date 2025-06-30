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
    batch_create_action_history,
    bulk_load_districts,
    bulk_load_complaints,
    bulk_load_action_histories,
    filter_api_request,
    record_api_request_success,
    mark_api_request_failed,
)
from ..db.session import get_db
from . import OFFICE, STATUS
from app.config import settings
import asyncio
import httpx
from typing import List, Tuple

class IngestionOrchestrator:
    def __init__(self, db: Session, semaphore_value: int = 10):
        self.client = JanasunaniAPIClient()
        self.s3 = boto3.client('s3')
        self.bucket_name = 'grievance-raw-data'
        self.db = db
        self.semaphore = asyncio.Semaphore(semaphore_value)

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

    async def ingest_districts(self):
        """Ingest district data."""
        try:
            districts = await self.client.get_districts()
            districts_validated = validate(districts, District, dict_mode=False)
            
            # Store data in database using CRUD operations
            stored_districts = bulk_load_districts(self.db, districts_validated)
            logger.info(f"Successfully stored {len(stored_districts)} districts in database")
            
            return districts_validated
        except Exception as e:
            logger.error(f"Error ingesting districts: {e}")
            raise

    async def ingest_complaints(self, year: int, distId: int, status: int, office: int) -> list[Complaint]:
        """Ingest complaint data."""
        try:
            complaints = await self.client.get_complaints(year, distId, status, office)
            complaints_validated = validate(complaints, Complaint, dict_mode=False)
            
            # Store data in database using CRUD operations
            stored_complaints = bulk_load_complaints(self.db, complaints_validated)
            logger.info(f"Successfully stored {len(stored_complaints)} complaints in database")
            
            return complaints_validated
        except Exception as e:
            # logger.error(f"Error ingesting complaints: {e}")
            raise
    
    async def limited_ingest_complaints(self, year: int, distId: int, status: int, office: int) -> list[Complaint]:
        """Ingest complaint data with limited concurrency."""
        async with self.semaphore:
            try:
                return await self.ingest_complaints(year, distId, status, office)
            except JanasunaniAPIError as e:
                logger.warning(f"{e}")
                return []
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error: {e}")
                if "Too Many Requests" in str(e).lower():
                    await asyncio.sleep(1)  # Wait xx seconds before retrying
                    return await self.ingest_complaints(year, distId, status, office)
                else:
                    return []
            except httpx.RequestError as e:
                logger.error(f"Request error: {e}")
                return []
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                return []

    async def ingest_action_history(self, ticket_no: str) -> list[ActionHistory]:
        """Ingest action history data."""
        try:
            action_history = await self.client.get_action_history(ticket_no)
            action_history_validated = validate_action_history(items=action_history, ticket_no=ticket_no, dict_mode=False)

            # Store data in database using CRUD operations
            stored_action_history = bulk_load_action_histories(self.db, action_history_validated)
            logger.info(f"Successfully stored {len(stored_action_history)} action history in database")

            return action_history_validated
        except Exception as e:
            # logger.error(f"Error ingesting action history: {e}")
            raise

    async def limited_ingest_action_history(self, ticket_no: str) -> list[ActionHistory]:
        """Ingest action history data with limited concurrency."""
        async with self.semaphore:
            try:
                return await self.ingest_action_history(ticket_no)
            except JanasunaniAPIError as e:
                logger.warning(f"{e}")
                return []
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error: {e}")
                if "too many requests" in str(e).lower():
                    await asyncio.sleep(10)  # Wait xx seconds before retrying
                    return await self.ingest_action_history(ticket_no)
                else: 
                    return []
            except httpx.RequestError as e:
                logger.error(f"Request error: {e}")
                return []
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                return []
            

async def run_ingestion_service(force_params: List[Tuple[int, int, int, int]] = None):
    """Main async ingestion service runner."""
    days_threshold = 7
    max_retries = 3
    try:
        db = next(get_db())
        orchestrator = IngestionOrchestrator(db,5)
        
        # Ingest districts
        districts = await orchestrator.ingest_districts() # does this get all districts?

        # Generate initial set of all possible combinations
        params = [(year, district.dist_id, status, office) 
                       for year in range(2021, datetime.now().year) 
                       for district in districts 
                       for status in STATUS.keys() 
                       for office in OFFICE.keys()]
    

        for param in params:
            if filter_api_request(db, *param, days_threshold=days_threshold):
                params.remove(param)
        
        if force_params:
            params.extend(force_params)

        logger.info(f"Total complaint requests to process: {len(params)}")

        try:
            tasks = [orchestrator.limited_ingest_complaints(*param) for param in params]
            complaints = await asyncio.gather(*tasks, return_exceptions=True)            
            flattened_complaints = []
            for result, (year, dist_id, status, office) in zip(complaints, params):
                if isinstance(result, list):
                    flattened_complaints.extend(result)
                    record_api_request_success(db, year, dist_id, status, office, len(result))
                elif isinstance(result, Exception):
                    logger.error(f"Failed to process year={year}, dist={dist_id}, status={status}, office={office}: {result}")
                    mark_api_request_failed(db, year, dist_id, status, office, str(result)) # anywhere else to log this?
            
            logger.info(f"Completed {len(complaints)} complaint ingestion tasks")
        except Exception as e:
            logger.error(f"Error in complaint ingestion: {e}")
        
        # Ingest action history for each complaint
        try:
            logger.info(f"Processing action history for {len(flattened_complaints)} complaints")
            tasks = [orchestrator.limited_ingest_action_history(complaint.ticket_no) for complaint in flattened_complaints]
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Error in action history ingestion: {e}")
        
        logger.info("Data ingestion completed successfully")
        return {
            'statusCode': 200,
            'body': json.dumps('Data ingestion completed successfully')
        }
        
    except Exception as e:
        logger.error(f"Error in ingestion service: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }
    finally:
        db.close()
    
if __name__ == "__main__":
    asyncio.run(run_ingestion_service())