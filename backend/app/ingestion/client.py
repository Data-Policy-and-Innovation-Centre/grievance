import httpx
import asyncio
from app.config import settings, directories
from .schemas import validate, validate_action_history, Complaint, District
from loguru import logger
from . import STATUS, OFFICE
from datetime import datetime
from more_itertools import chunked
from itertools import product
import json
import functools

RETRY_BACKOFF = 5
MAX_RETRIES = 10

class JanasunaniAPIError(Exception):
    """Custom exception for Jansunani API errors."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

def with_retry(max_retries: int = MAX_RETRIES, backoff: int = RETRY_BACKOFF):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            label = kwargs.pop("label", func.__name__)
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except ValueError:
                    raise
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        retry_after = int(e.response.headers.get("Retry-After", backoff))
                        logger.warning(f"[429] {label}: retrying in {retry_after}s...")
                        await asyncio.sleep(retry_after)
                    else:
                        logger.error(f"[{label}] HTTP error: {e}")
                        break
                except Exception as e:
                    logger.error(f"[{label}] Other error: {e}")
                    break
            logger.error(f"[{label}] Failed after {max_retries} retries.")
            return None
        return wrapper
    return decorator

class JanasunaniAPIClient:
    """
    Async client for the Jansunani grievance API using httpx.
    """

    def __init__(
        self,
        base_url: str = settings.JANASUNANI_API_BASE_URL,
        auth: tuple = (
            settings.JANASUNANI_API_USERNAME,
            settings.JANASUNANI_API_PASSWORD,
        ),
    ):
        self.base_url = base_url
        self.auth = auth

    def _handle_response(self, response: httpx.Response) -> dict:
        """
        Handles the API response from a requests call.

        Args:
            response (requests.Response): The HTTP response object to process.

        Returns:
            dict: The parsed response data from either the 'distRes' or 'Res' key.

        Raises:
            JansunaniAPIError: If neither 'distRes', 'Res' or 'actionHistory' is found in the response,
                or if the API returns an error status.
            requests.HTTPError: If the HTTP response status code is not 200.
        """
        if response.status_code == 200:
            response_json = response.json()
            message = response_json.get("message", "")
            status = response_json.get("status", "")
            if status == 200:
                if "distRes" in response_json:
                    return response_json["distRes"]
                elif "Res" in response_json:
                    return response_json["Res"]
                elif "actionHistory" in response_json:
                    return response_json["actionHistory"]
                else:
                    raise JanasunaniAPIError(
                        "Neither 'distRes', 'Res' or 'actionHistory' found in response."
                    )
            elif status == 204:
                pass
            else:
                raise JanasunaniAPIError(
                    f"Jansunani API returned an error: {message} (Status: {status})"
                )
        else:
            response.raise_for_status()

    def get_districts(self) -> dict:
        """
        Fetches the list of districts from the remote API.

        Returns:
            dict: A dictionary containing the districts data as returned by the API.

        Raises:
            JanasunaniAPIError: If the HTTP request fails.
        """
        logger.info("Fetching districts from Jansunani API (async)...")
        url = f"{self.base_url}/getDistricts"
        with httpx.Client(auth=self.auth) as client:
            response = client.get(url)
            return self._handle_response(response)

    @with_retry()
    async def get_complaints(self, year: int, distId: int, status: int, office: int, semaphore: asyncio.Semaphore) -> list[dict]:
        """
        Retrieves complaints from the grievance system based on the specified filters.

        Args:
            year (int): The year for which to retrieve complaints.
            distId (int): The district ID to filter complaints.
            status (int): The status code to filter complaints.
            office (int): The office ID to filter complaints.

        Returns:
            list[dict]: The response data containing the filtered complaints.

        Raises:
            JanasunaniAPIError: If the HTTP request fails.
            ValueError: If the input parameters are invalid.
        """
        if status not in STATUS.keys():
            raise ValueError(f"Status must be in {STATUS.keys()}")
        
        if office not in OFFICE.keys():
            raise ValueError(f"Office must be in {OFFICE.keys()}")

        
        logger.info(
                f"Fetching complaints for year: {year}, district ID: {distId}, status: {STATUS[status]}, office: {OFFICE[office]} (async)"
            )
        url = f"{self.base_url}/getGrievanceDetails"
        params = {"year": year, "distId": distId, "status": status, "office": office}
        async with semaphore:
            await asyncio.sleep(0.5)
            timeout = httpx.Timeout(
                connect=15.0,  # time to establish connection
                read=60.0,     # max time to wait for server response **after** connection
                write=15.0,    # max time to send request
                pool=120.0     # max time to wait for a connection from pool
                )
            async with httpx.AsyncClient(auth=self.auth, timeout=timeout) as client:
                response = await client.get(url, params=params)
                return self._handle_response(response)

    @with_retry()
    async def get_action_history(self, ticket_no: str, semaphore: asyncio.Semaphore) -> list[dict]:
        """
        Retrieves action history for a given ticket number from the grievance system.

        Args:
            ticket_no (str): The ticket number for which to retrieve the action history.

        Returns:
            list[dict]: The response data containing the action history.

        Raises:
            JanasunaniAPIError: If the HTTP request fails.
        """
        logger.info(f"Fetching action history for ticket number: {ticket_no} (async)")
        url = f"{self.base_url}/getGrievanceHistory"
        params = {"ticketNumber": ticket_no}
        async with semaphore:
            await asyncio.sleep(0.5)
            timeout = httpx.Timeout(15.0)
            async with httpx.AsyncClient(auth=self.auth, timeout=timeout) as client:
                response = await client.get(url, params=params)
                return self._handle_response(response)

logger.remove()  # Remove default stderr sink
logger.add(directories.LOGS / "client_log.txt", level="INFO")

from tqdm.asyncio import tqdm
# Wrap each task to update the tqdm bar when done
async def track_with_progress(coros, desc="Processing"):
    results = []
    total = len(coros)

    # tqdm.asyncio is smart about async display updates
    with tqdm(total=total, desc=desc, ncols=100) as pbar:
        async def wrapped(coro):
            try:
                result = await coro
                return result
            finally:
                pbar.update(1)

        tasks = [wrapped(coro) for coro in coros]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    return results

async def main():
    client = JanasunaniAPIClient()
    districts = client.get_districts()
    districts_validated = validate(districts, District)

    semaphore = asyncio.Semaphore(10)
    year_lst = range(2025, datetime.now().year + 1) # TODO: change to range(2021, datetime.now().year + 1)
    dist_list = [dist['dist_id'] for dist in districts_validated]
    complaint_params = list(product(year_lst, dist_list, STATUS.keys(), OFFICE.keys()))
    tasks_complaints = [
        client.get_complaints(year, dist, status, office, semaphore, label=f"complaints-{year}-{dist}-{status}-{office}")
        for year, dist, status, office in complaint_params
        ]    

    complaints = []
    for subtask_complaint in chunked(tasks_complaints, 10):
        await asyncio.sleep(5)
        result = await track_with_progress(subtask_complaint, desc="Ingesting complaints")
        complaints.extend(r for r in result if r is not None)
    
    flatten_complaints = [complaint for sublist in complaints if isinstance(sublist, list) for complaint in sublist]
    complaints_validated = validate(flatten_complaints, Complaint, dict_mode=False)

    # path_complaint = f"./data/raw/flatten_complaints_{dist_list[0]}.json"
    # with open(path_complaint, 'w') as f:
    #     json.dump(flatten_complaints, f)


    ticket_nos = [complaint.ticket_no for complaint in complaints_validated]
    
    semaphore = asyncio.Semaphore(10)
    tasks = [
        client.get_action_history(ticket, semaphore, label=f"action-{ticket}")
        for ticket in ticket_nos
        ]

    action_history = []
    for subtask in chunked(tasks, 30):
        await asyncio.sleep(5)
        result = await track_with_progress(subtask, desc="Ingesting actions")
        action_history.extend(r for r in result if r is not None)

    # path_actions = f"./data/raw/actions_{dist_list[0]}.json"
    # with open(path_actions, 'w') as f:
    #     json.dump(action_history, f)

    # action_history_validated = []
    # for ix, ticket_no in enumerate(ticket_nos):
    #     action_history_validated.extend(validate_action_history(action_history[ix], ticket_no, dict_mode = False))

if __name__ == "__main__":
    asyncio.run(main())