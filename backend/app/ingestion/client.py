import requests
from app.config import settings
from .schemas import validate, Complaint, District
from loguru import logger
from . import STATUS, OFFICE


class JanasunaniAPIError(Exception):
    """Custom exception for Jansunani API errors."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class JanasunaniAPIClient:
    """
    JansunaniAPIClient provides methods to interact with the Jansunani grievance API.

    This client handles authentication, request construction, and response parsing for
    the Jansunani API endpoints. It provides methods to fetch district information and
    retrieve complaints based on various filters.

    Attributes:
        base_url (str): The base URL for the Jansunani API.
        auth (tuple): A tuple containing the username and password for API authentication.

    Methods:
        get_districts() -> dict:

        get_complaints(year: int, distId: int, status: int, office: int) -> dict:

        JansunaniAPIError: For API-specific errors or unexpected response formats.
        requests.RequestException: For network-related errors during HTTP requests.
        requests.HTTPError: For non-200 HTTP responses.
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

    def _handle_response(self, response: requests.Response) -> dict:
        """
        Handles the API response from a requests call.

        Args:
            response (requests.Response): The HTTP response object to process.

        Returns:
            dict: The parsed response data from either the 'distRes' or 'Res' key.

        Raises:
            JansunaniAPIError: If neither 'distRes' nor 'Res' is found in the response,
                or if the API returns an error status.
            requests.HTTPError: If the HTTP response status code is not 200.
        """
        if response.status_code == 200:
            response = response.json()
            message = response.get("message", "")
            status = response.get("status", "")
            if status == 200:
                if "distRes" in response:
                    return response["distRes"]
                elif "Res" in response:
                    return response["Res"]
                else:
                    raise JanasunaniAPIError(
                        "Neither 'distRes' nor 'Res' found in response."
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
            requests.RequestException: If the HTTP request fails.
            ValueError: If the response cannot be handled or parsed.
        """
        logger.info("Fetching districts from Jansunani API...")
        url = f"{self.base_url}/getDistricts"
        response = requests.get(url, auth=self.auth)
        return self._handle_response(response)

    def get_complaints(self, year: int, distId: int, status: int, office: int) -> dict:
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
            requests.RequestException: If the HTTP request fails.
            ValueError: If the response cannot be handled or parsed.
        """
        if status not in STATUS.keys():
            raise ValueError(f"Status must be in {STATUS.keys()}")
        
        if office not in OFFICE.keys():
            raise ValueError(f"Office must be in {OFFICE.keys()}")

        
        logger.info(
                f"Fetching complaints for year: {year}, district ID: {distId}, status: {STATUS[status]}, office: {OFFICE[office]}\n"
            )
        url = f"{self.base_url}/getGrievanceDetails"
        params = {"year": year, "distId": distId, "status": status, "office": office}
        response = requests.get(url, params=params, auth=self.auth)
        return self._handle_response(response)


if __name__ == "__main__":
    client = JanasunaniAPIClient()
    try:
        districts = client.get_districts()
        districts_validated = validate(districts, District)
        complaints = client.get_complaints(2025, status=1, distId=344, office=4)
        complaints_validated = validate(complaints, Complaint)
    except requests.RequestException as e:
        print(f"An error occurred: {e}")
