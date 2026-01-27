"""Exceptions for C&D Iot integration."""


class MySmartHomeError(Exception):
    """Base exception for C&D Iot integration."""


class NetworkError(MySmartHomeError):
    """Raised when network communication fails."""


class AuthenticationError(NetworkError):
    """Raised when authentication fails."""


class DeviceError(MySmartHomeError):
    """Raised when device communication fails."""


class InvalidDeviceError(MySmartHomeError):
    """Raised when device ID or type is invalid."""


class DeviceTimeoutError(NetworkError):
    """Raised when device communication times out."""


class DeviceOfflineError(DeviceError):
    """Raised when device is offline."""


class InvalidResponseError(NetworkError):
    """Raised when receiving invalid response from device."""


class InvalidStateError(DeviceError):
    """Raised when device state is invalid."""


class BatchQueryError(DeviceError):
    """Raised when batch query fails."""


class StateUpdateError(DeviceError):
    """Raised when state update fails."""
