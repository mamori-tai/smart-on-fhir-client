import abc
from typing import Set

from aiohttp import ClientSession
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
        self, strategy: Strategy, session: ClientSession
    ):
        if not strategy in self.supported_strategies:
            return
        if strategy is Strategy.M2M:
            return await self.get_access_token_for_m2m(session)
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
