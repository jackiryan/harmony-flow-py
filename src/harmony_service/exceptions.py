"""Module defining harmony service errors raised by harmony-flow service."""

from harmony_service_lib.util import HarmonyException

SERVICE_NAME = "harmony-flow"


class VectorFlowServiceError(HarmonyException):
    """Base service exception."""

    def __init__(self, message=None):
        """All service errors are assocated with SERVICE_NAME."""
        super().__init__(message=message, category=SERVICE_NAME)


class VectorFlowInvalidMessageError(VectorFlowServiceError):
    """Input Harmony Message could not be used as presented."""
