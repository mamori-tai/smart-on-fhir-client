import abc
import enum
from typing import Set

from aiohttp import ClientSession
from loguru import logger
from pydantic import BaseModel

from smart_on_fhir_client.strategy import Strategy, StrategyNotFound


class Partner(BaseModel, abc.ABC):
    """Base client"""

    name: str
    supported_strategies: Set[Strategy]
    client_id: str | None
    client_secret: str | None
    token_url: str | None
    authorize_url: str | None
    fhir_url: str | None

    async def get_access_token_for_strategy(
        self, strategy: Strategy, session: ClientSession, **kwargs
    ):
        if not strategy in self.supported_strategies:
            logger.info(f"{strategy=} is not supported for partner {self.name=}")
            return

        # enumerate here all strategies...
        if strategy is Strategy.M2M:
            return await self.get_access_token_for_m2m(session, **kwargs)
        raise StrategyNotFound("Strategy not found")

    def attrs(self, *attr_name):
        return dict([(name, getattr(self, name)) for name in attr_name])

    @abc.abstractmethod
    async def get_access_token_for_m2m(self, session: ClientSession) -> str:
        ...

    async def trade_refresh_for_access_token(self, refresh_token: str):
        ...

    @abc.abstractmethod
    async def get_key_as_json(self, session):
        ...


class TargetUrlStrategy(enum.Enum):
    NONE = enum.auto()
    PARTNER = enum.auto()
    ORGANIZATION_NAME = enum.auto()


class Organization:
    def __init__(
        self,
        name: str,
        target_url_strategy: TargetUrlStrategy = TargetUrlStrategy.PARTNER,
        **kwargs,
    ):
        self.name = name
        self.target_url_strategy = target_url_strategy
        self.parameters = kwargs

    @property
    def slug(self):
        return self.name.replace(" ", "-").replace("/", "").upper()
