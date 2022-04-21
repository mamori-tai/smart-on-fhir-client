import enum


class StrategyNotFound(Exception):
    """Strategy not found for the client i.e. the client does not
    support the wanted strategy
    """

    ...


class M2MAccessTokenError(Exception):
    """An error occurred during fetch of the access token
    in an M2M authentication"""

    ...


class Strategy(enum.Enum):
    """Different kind of strategy to get the graal
    i.e. the access token in order to make fhir request"""

    M2M = enum.auto()
