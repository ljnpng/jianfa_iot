"""Test HttpClient."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from custom_components.jianfa_iot.http_client import HttpClient
from custom_components.jianfa_iot.models import Room, RoomList

@pytest.mark.asyncio
async def test_get_room_list_success(hass):
    """Test successful room list retrieval."""
    # Mock the HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {}
    mock_response.json = AsyncMock(return_value={
        "code": 200,
        "msg": "操作成功",
        "total": "1",
        "rows": [{
            "roomId": "test-room-id-1234567890abcdef",
            "communityId": "test-community-id-1234567890",
            "communityCode": "001",
            "communityName": "测试社区服务中心",
            "gateway": "TEST-GATEWAY:86100c00fffe008000000040e2501a1f",
            "easId": "test-eas-id",
            "roomName": "测试10号楼 B梯 303",
            "buildingName": "10#",
        }]
    })
    mock_response.raise_for_status = MagicMock()

    with patch.object(hass.helpers.aiohttp_client.async_get_clientsession(), 'get') as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_response

        client = HttpClient(hass, x_token="test-token", phone="13800138000")
        room_list = await client.get_room_list()

        assert isinstance(room_list, RoomList)
        assert room_list.total == 1
        assert len(room_list.rooms) == 1
        assert room_list.first_room is not None
        assert room_list.first_room.room_id == "test-room-id-1234567890abcdef"
        assert room_list.first_room.community_id == "test-community-id-1234567890"
