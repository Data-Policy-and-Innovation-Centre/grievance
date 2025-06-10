import pytest
from unittest.mock import patch, MagicMock
from app.ingestion.client import JanasunaniAPIClient, JanasunaniAPIError

@pytest.fixture
def client():
    return JanasunaniAPIClient(base_url="http://fake-url", auth=("user", "pass"))

class TestJansunaniAPIClient:
    @patch("app.ingestion.client.requests.get")
    def test_get_districts_success(self, mock_get, client: JanasunaniAPIClient):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": 200,
            "message": "Success",
            "distRes": {"districts": [{"id": 1, "name": "District1"}]}
        }
        mock_get.return_value = mock_response

        result = client.get_districts()
        assert result == {"districts": [{"id": 1, "name": "District1"}]}
        mock_get.assert_called_once_with("http://fake-url/getDistricts", auth=("user", "pass"))

    @patch("app.ingestion.client.requests.get")
    def test_get_complaints_success(self, mock_get, client: JanasunaniAPIClient):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": 200,
            "message": "Success",
            "Res": {"complaints": [{"id": 123, "desc": "Test"}]}
        }
        mock_get.return_value = mock_response

        result = client.get_complaints(year=2024, distId=1, status=2, office=0)
        assert result == {"complaints": [{"id": 123, "desc": "Test"}]}
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert args[0] == "http://fake-url/getGrievanceDetails"
        assert kwargs["params"] == {"year": 2024, "distId": 1, "status": 2, "office": 0}

    @patch("app.ingestion.client.requests.get")
    def test_handle_response_missing_keys(self, mock_get, client: JanasunaniAPIClient):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": 200,
            "message": "Success"
        }
        mock_get.return_value = mock_response

        with pytest.raises(JanasunaniAPIError, match="Neither 'distRes' nor 'Res' found in response."):
            client.get_districts()

    @patch("app.ingestion.client.requests.get")
    def test_handle_response_api_error_status(self, mock_get, client: JanasunaniAPIClient):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": 400,
            "message": "Bad Request"
        }
        mock_get.return_value = mock_response

        with pytest.raises(JanasunaniAPIError, match="Jansunani API returned an error: Bad Request"):
            client.get_districts()

    @patch("app.ingestion.client.requests.get")
    def test_handle_response_http_error(self, mock_get, client: JanasunaniAPIClient):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        mock_get.return_value = mock_response

        with pytest.raises(Exception, match="HTTP Error"):
            client.get_districts()