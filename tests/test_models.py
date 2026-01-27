"""Test data models."""
import pytest
from custom_components.jianfa_iot.models import Room, RoomList

def test_room_creation():
    """Test Room dataclass creation."""
    room = Room(
        room_id="test-room-123",
        community_id="comm-456",
        community_code="35020369",
        community_name="Test Community",
        gateway="XMSLYL-TEST:123",
        eas_id="test-eas",
        room_name="Test Room",
        building_name="Building 1",
    )

    assert room.room_id == "test-room-123"
    assert room.community_id == "comm-456"
    assert room.community_code == "35020369"
    assert room.room_name == "Test Room"

def test_room_build_headers():
    """Test building headers from room config."""
    room = Room(
        room_id="room-1",
        community_id="comm-1",
        community_code="001",
        community_name="Community 1",
        gateway="gw-1",
        eas_id="eas-1",
        room_name="Room 1",
    )

    headers = room.build_headers(
        token="test-token",
        phone="13800138000"
    )

    assert headers["X-token"] == "test-token"
    assert headers["space-phone"] == "13800138000"
    assert headers["roomid"] == "room-1"
    assert headers["communityId"] == "comm-1"
    assert headers["communityCode"] == "001"
    assert headers["communityName"] == "Community 1"
    assert headers["space-yr"] == "comm-1"
    assert headers["easId"] == "eas-1"
    assert headers["gateway"] == "gw-1"

def test_room_list_first_room():
    """Test RoomList.first_room property."""
    room1 = Room(
        room_id="room-1",
        community_id="comm-1",
        community_code="001",
        community_name="Community 1",
        gateway="gw-1",
        eas_id="eas-1",
        room_name="Room 1",
    )

    room2 = Room(
        room_id="room-2",
        community_id="comm-2",
        community_code="002",
        community_name="Community 2",
        gateway="gw-2",
        eas_id="eas-2",
        room_name="Room 2",
    )

    room_list = RoomList(total=2, rooms=[room1, room2])

    assert room_list.first_room == room1
    assert room_list.first_room.room_id == "room-1"

def test_room_list_empty():
    """Test RoomList with no rooms."""
    room_list = RoomList(total=0, rooms=[])

    assert room_list.first_room is None
    assert room_list.total == 0
