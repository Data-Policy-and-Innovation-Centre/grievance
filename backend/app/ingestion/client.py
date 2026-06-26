import asyncio
import functools

import httpx
from loguru import logger

from app.config import settings

from . import OFFICE, STATUS

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
            for _ in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except ValueError:
                    raise
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        retry_after = int(
                            e.response.headers.get("Retry-After", backoff)
                        )
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
                raise JanasunaniAPIError(
                    f"Jansunani API returned a 204 No Content: {message}"
                )
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
    async def get_complaints(
        self,
        year: int,
        distId: int,
        status: int,
        office: int,
        semaphore: asyncio.Semaphore,
    ) -> list[dict]:
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
                read=60.0,  # max time to wait for server response **after** connection
                write=15.0,  # max time to send request
                pool=120.0,  # max time to wait for a connection from pool
            )
            async with httpx.AsyncClient(auth=self.auth, timeout=timeout) as client:
                response = await client.get(url, params=params)
                return self._handle_response(response)

    @with_retry()
    async def get_action_history(
        self, ticket_no: str, semaphore: asyncio.Semaphore
    ) -> list[dict]:
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


async def main():
    pass


if __name__ == "__main__":
    asyncio.run(main())
