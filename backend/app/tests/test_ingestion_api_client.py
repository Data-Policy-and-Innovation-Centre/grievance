import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from app.ingestion.client import JanasunaniAPIClient, JanasunaniAPIError
import httpx

@pytest.fixture
def client():
    return JanasunaniAPIClient(base_url="http://fake-url", auth=("user", "pass"))

class TestJansunaniAPIClient:
    @pytest.mark.asyncio
    @patch("app.ingestion.client.httpx.AsyncClient")
    async def test_get_districts_success(self, mock_async_client, client: JanasunaniAPIClient):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": 200,
            "message": "Success",
            "distRes": {"districts": [{"id": 1, "name": "District1"}]}
        }
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        
        result = await client.get_districts()
        assert result == {"districts": [{"id": 1, "name": "District1"}]}
        mock_client_instance.get.assert_called_once_with("http://fake-url/getDistricts")

    @pytest.mark.asyncio
    @patch("app.ingestion.client.httpx.AsyncClient")
    async def test_get_complaints_success(self, mock_async_client, client: JanasunaniAPIClient):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": 200,
            "message": "Success",
            "Res": {"complaints": [{"id": 123, "desc": "Test"}]}
        }
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        
        result = await client.get_complaints(year=2024, distId=1, status=2, office=4)
        assert result == {"complaints": [{"id": 123, "desc": "Test"}]}
        mock_client_instance.get.assert_called_once()
        args, kwargs = mock_client_instance.get.call_args
        assert args[0] == "http://fake-url/getGrievanceDetails"
        assert kwargs["params"] == {"year": 2024, "distId": 1, "status": 2, "office": 4}

    @pytest.mark.asyncio
    async def test_get_complaints_wrong_params(self, client: JanasunaniAPIClient):
        with pytest.raises(ValueError, match="Status must be in"):
            await client.get_complaints(year=2024, distId=1, status=3, office=4)
        with pytest.raises(ValueError, match="Office must be in"):
            await client.get_complaints(year=2024, distId=1, status=2, office=8)

    @pytest.mark.asyncio
    @patch("app.ingestion.client.httpx.AsyncClient")
    async def test_handle_response_missing_keys(self, mock_async_client, client: JanasunaniAPIClient):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": 200,
            "message": "Success"
        }
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        
        with pytest.raises(JanasunaniAPIError, match="Neither 'distRes', 'Res' or 'actionHistory' found in response."):
            await client.get_districts()

    @pytest.mark.asyncio
    @patch("app.ingestion.client.httpx.AsyncClient")
    async def test_handle_response_api_error_status(self, mock_async_client, client: JanasunaniAPIClient):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": 400,
            "message": "Bad Request"
        }
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        
        with pytest.raises(JanasunaniAPIError, match="Jansunani API returned an error: Bad Request"):
            await client.get_districts()

    @pytest.mark.asyncio
    @patch("app.ingestion.client.httpx.AsyncClient")
    async def test_handle_response_http_error(self, mock_async_client, client: JanasunaniAPIClient):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("HTTP Error", request=MagicMock(), response=mock_response)
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_districts()

    @pytest.mark.asyncio
    @patch("app.ingestion.client.httpx.AsyncClient")
    async def test_get_action_history_success(self, mock_async_client, client: JanasunaniAPIClient):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": 200,
            "message": "Success",
            "actionHistory": {"actions": [{"id": 1, "action": "Test Action"}]}
        }
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        
        result = await client.get_action_history("T123")
        assert result == {"actions": [{"id": 1, "action": "Test Action"}]}
        mock_client_instance.get.assert_called_once()
        args, kwargs = mock_client_instance.get.call_args
        assert args[0] == "http://fake-url/getGrievanceHistory"
        assert kwargs["params"] == {"ticketNumber": "T123"}

    @pytest.mark.asyncio
    @patch("app.ingestion.client.httpx.AsyncClient")
    async def test_handle_response_action_history(self, mock_async_client, client: JanasunaniAPIClient):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": 200,
            "message": "Success",
            "actionHistory": {"actions": [{"id": 1, "action": "Test Action"}]}
        }
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance
        
        result = await client.get_action_history("T123")
        assert result == {"actions": [{"id": 1, "action": "Test Action"}]}