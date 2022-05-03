import json
import pickle
from json import JSONDecodeError
from typing import Type, Callable, NoReturn

import aiohttp
from aiohttp import ClientSession
from fhirpy.base.exceptions import ResourceNotFound, OperationOutcome
from fhirpy.base.utils import (
    AttrDict,
)
from fhirpy.lib import AsyncFHIRClient
from loguru import logger
from seito.monad.async_opt import aopt
from tenacity import retry, stop_after_attempt, retry_if_exception_type

from smart_on_fhir_client.partner import Partner, Organization
from smart_on_fhir_client.requester.fhir_reference import CustomFHIRReference
from smart_on_fhir_client.requester.fhir_resource import CustomFHIRResource
from smart_on_fhir_client.strategy import Strategy
from smart_on_fhir_client.utils import mixin


class UnauthorizedError(Exception):
    ...


@mixin
class RefreshTokenHandlerMixin:
    async def trade_refresh_token_to_access_token(self):
        try:
            response = await self.client.trade_refresh_for_access_token(
                self.refresh_token
            )
            return response["access_token"], response["refresh_token"]
        except KeyError as e:
            logger.error(e)
            raise e
        except:
            raise


class SmartOnFhirClient(RefreshTokenHandlerMixin, AsyncFHIRClient):
    """
    Simply overrides the _do_request methods to perform exponential backoff
    and retries
    """

    def __init__(
        self,
        url,
        authorization=None,
        extra_headers=None,
        refresh_token=None,
        partner=None,
        fhir_manager=None,
        strategy=None,
        organization=None,
    ):
        super(AsyncFHIRClient, self).__init__(url, authorization, extra_headers)
        self.refresh_token = refresh_token
        self.partner = partner
        self.fhir_manager = fhir_manager
        self.strategy = strategy
        self.organization = organization

    @property
    def client_name(self):
        return (
            self.organization.slug
            if self.organization is not None
            else self.partner_name
        )

    @property
    def partner_name(self):
        return self.partner.name

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception_type(UnauthorizedError))
    async def _retry(self, method, path, data=None, params=None):
        # if we do not have an authorization token
        # try fetch one
        if not self.authorization:
            await self.fetch_access_token()

        headers = self._build_request_headers()
        url = self._build_request_url(path, params)
        logger.debug("Fetching {}", url)
        async with aiohttp.request(method, url, json=data, headers=headers) as r:
            if 200 <= r.status < 300:
                data = await r.text()
                return json.loads(data, object_hook=AttrDict)

            if r.status == 404 or r.status == 410:
                raise ResourceNotFound(await r.text())

            if r.status == 403 or r.status == 401:
                # retry with a refresh token
                access, refresh = await self.trade_refresh_token_to_access_token()
                self.authorization = f"Bearer {access}"
                self.refresh_token = refresh
                raise UnauthorizedError("Retrying because of unauthorized")

            data = await r.text()
            try:
                parsed_data = json.loads(data)
                if parsed_data["resourceType"] == "OperationOutcome":
                    raise OperationOutcome(resource=parsed_data)
                raise OperationOutcome(reason=data)
            except (KeyError, JSONDecodeError):
                raise OperationOutcome(reason=data)

    async def _do_request(self, method, path, data=None, params=None):
        return await self._retry(method, path, data=data, params=params)

    async def fetch_access_token(self):
        logger.debug(f"Trying to fetch access token for {self.client_name=}")
        session = smart_client_factory.session
        try:
            access_token = await self.partner.get_access_token_for_strategy(
                self.strategy,
                session,
                **(
                    self.organization.parameters
                    if self.organization is not None
                    else {}
                ),
            )
        except:
            logger.warning(f"Unable to fetch access token for {self.client_name=}")
            raise UnauthorizedError("Can not get access token")
        else:
            self.authorization = f"Bearer {access_token}"

    def reference(self, resource_type=None, id=None, reference=None, **kwargs):
        if resource_type and id:
            reference = "{0}/{1}".format(resource_type, id)

        if not reference:
            raise TypeError(
                "Arguments `resource_type` and `id` or `reference` " "are required"
            )
        return CustomFHIRReference(
            self.fhir_manager, self, reference=reference, **kwargs
        )

    def dumps(self):
        return pickle.dumps(self)

    def __str__(self):
        return f"< SmartOnFhirClient url={self.url} >"


class InvalidAccessToken(Exception):
    ...


class SmartOnFhirClientBuilder:
    def __init__(self, session: ClientSession):
        """

        Args:
            session:
        """
        self._partner: Partner | None = None
        self._strategy: Strategy | None = None
        self._organization: Organization | None = None
        self._session = session
        self._cls_by_resource = {}
        self._target_fhir_server_authorization: str | Callable[..., str] | None = None

    def _check_partner(self) -> NoReturn:
        """

        """
        if not self._partner:
            raise ValueError("No partner registered")

    def for_partner(self, client: Partner) -> "SmartOnFhirClientBuilder":
        """

        Args:
            client:

        Returns:

        """
        self._partner = client
        return self

    def for_strategy(self, strategy: Strategy) -> "SmartOnFhirClientBuilder":
        """

        Args:
            strategy:

        Returns:

        """
        self._check_partner()
        self._strategy = strategy
        return self

    def for_organization(
        self, organization: Organization
    ) -> "SmartOnFhirClientBuilder":
        """

        Args:
            organization:

        Returns:

        """
        self._check_partner()
        self._organization = organization
        return self

    def register_cls_for(
        self, resource: str, cls: Type[CustomFHIRResource]
    ) -> "SmartOnFhirClientBuilder":
        """

        Args:
            resource:
            cls:

        Returns:

        """
        self._check_partner()
        self._cls_by_resource[resource] = cls
        return self

    def register_target_server_authorization(
        self, jwt_token: str | Callable[..., str]
    ) -> "SmartOnFhirClientBuilder":
        """

        Args:
            jwt_token:

        Returns:

        """
        self._check_partner()
        self._target_fhir_server_authorization = jwt_token
        return self

    async def build(self, fhir_manager) -> SmartOnFhirClient:
        """
        build asynchronously a fhir client
        """

        def build_client(access_token):
            if access_token:
                logger.info(f"Successfully initialized {self._partner.name=} client !")
            else:
                logger.warning(
                    f"Unable to initialize {self._partner.name=} client...A retry will be performed at first call"
                )
            return SmartOnFhirClient(
                self._partner.fhir_url,
                authorization=f"Bearer {access_token}" if access_token else "",
                partner=self._partner,
                fhir_manager=fhir_manager,
                strategy=self._strategy,
                organization=self._organization,
            )

        return await (
            aopt(
                self._partner.get_access_token_for_strategy,
                self._strategy,
                session=self._session,
                **(
                    self._organization.parameters
                    if self._organization is not None
                    else {}
                ),
            )
            .map(build_client)
            .or_else(lambda: build_client(""))
        )


class SmartOnFhirBuilderFactory:
    def __init__(self):
        self._session = None

    async def init(self):
        """

        """
        self._session = ClientSession()

    def builder(self) -> SmartOnFhirClientBuilder:
        """

        Returns:

        """
        return SmartOnFhirClientBuilder(self._session)

    @property
    def session(self):
        """

        Returns:

        """
        return self._session

    async def close(self):
        """

        """
        await self._session.close()

    async def __aenter__(self):
        """

        Returns:

        """
        if self._session is None:
            await self.init()
        return await self._session.__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """

        Args:
            exc_type:
            exc_val:
            exc_tb:
        """
        await self._session.__aexit__(exc_type, exc_val, exc_tb)


smart_client_factory = SmartOnFhirBuilderFactory()
