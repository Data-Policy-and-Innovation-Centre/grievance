import httpx
import asyncio
from app.config import settings
from .schemas import validate, validate_action_history, Complaint, District
from loguru import logger
from . import STATUS, OFFICE


class JanasunaniAPIError(Exception):
    """Custom exception for Jansunani API errors."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


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

    async def _handle_response(self, response: httpx.Response) -> dict:
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
            else:
                raise JanasunaniAPIError(
                    f"Jansunani API returned an error: {message} (Status: {status})"
                )
        else:
            response.raise_for_status()

    async def get_districts(self) -> dict:
        """
        Fetches the list of districts from the remote API.

        Returns:
            dict: A dictionary containing the districts data as returned by the API.

        Raises:
            JanasunaniAPIError: If the HTTP request fails.
        """
        logger.info("Fetching districts from Jansunani API (async)...")
        url = f"{self.base_url}/getDistricts"
        async with httpx.AsyncClient(auth=self.auth) as client:
            response = await client.get(url)
            return await self._handle_response(response)

    async def get_complaints(self, year: int, distId: int, status: int, office: int) -> dict:
        """
        Retrieves complaints from the grievance system based on the specified filters.

        Args:
            year (int): The year for which to retrieve complaints.
            distId (int): The district ID to filter complaints.
            status (int): The status code to filter complaints.
            office (int): The office ID to filter complaints.

        Returns:
            dict: The response data containing the filtered complaints.

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
        async with httpx.AsyncClient(auth=self.auth) as client:
            response = await client.get(url, params=params)
            return await self._handle_response(response)
    
    async def get_action_history(self, ticket_no: str) -> dict:
        """
        Retrieves action history for a given ticket number from the grievance system.

        Args:
            ticket_no (str): The ticket number for which to retrieve the action history.

        Returns:
            dict: The response data containing the action history.

        Raises:
            JanasunaniAPIError: If the HTTP request fails.
        """
        logger.info(f"Fetching action history for ticket number: {ticket_no} (async)")
        url = f"{self.base_url}/getGrievanceHistory"
        params = {"ticketNumber": ticket_no}
        async with httpx.AsyncClient(auth=self.auth) as client:
            response = await client.get(url, params=params)
            return await self._handle_response(response)


async def main():
    client = JanasunaniAPIClient()
    try:
        districts = await client.get_districts()
        districts_validated = validate(districts, District)
        complaints = await client.get_complaints(2025, status=1, distId=344, office=4)
        complaints_validated = validate(complaints, Complaint)

        # Get action history
        try:
            ticket_no = complaints_validated[0].ticket_no
        except AttributeError:
            ticket_no = complaints_validated[0]['ticket_no']
        
        action_history = await client.get_action_history(ticket_no)
        action_history = validate_action_history(action_history, ticket_no)
        print(action_history)
    except httpx.RequestError as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    asyncio.run(main())
