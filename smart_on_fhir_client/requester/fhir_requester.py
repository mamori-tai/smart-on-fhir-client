import os
import warnings
from collections import defaultdict
from typing import Type, Union, NoReturn, Any, TypeVar

from fhir.resources.identifier import Identifier
from fhir.resources.reference import Reference
from fhir.resources.resource import Resource
from fhirpy.base import AsyncResource
from fhirpy.lib import AsyncFHIRResource
from seito.monad.try_ import try_

from smart_on_fhir_client.client import SmartOnFhirClientBuilder, SmartOnFhirClient
from smart_on_fhir_client.partner import Partner
from smart_on_fhir_client.requester.fhir_resource import CustomFHIRResource


class SearchSet:
    """
    Wrapper around fhir client class to perform auto conversion
    to pydantic model if needed
    """

    def __init__(self, search, fhir_manager, client):
        self._search = search
        self._fhir_manager = fhir_manager
        self._client = client

    def _process_result(self, result, return_as: Type):
        if result is None:
            return result
        if return_as is not None:
            return return_as(**result)
        return self._fhir_manager.create_async_fhir_resource(self._client, result)

    def limit(self, value):
        return SearchSet(self._search.limit(value), self._fhir_manager, self._client)

    def sort(self, value):
        return SearchSet(self._search.sort(value), self._fhir_manager, self._client)

    def revinclude(self, value):
        return SearchSet(
            self._search.revinclude(value), self._fhir_manager, self._client
        )

    def include(self, *args, **kwargs):
        return SearchSet(
            self._search.include(*args, **kwargs), self._fhir_manager, self._client
        )

    async def fetch_raw(self, return_as=None):
        result = await self._search.fetch_raw()
        return self._process_result(result, return_as=return_as)

    async def fetch(self, return_as=None):
        # maybe wrap in attempt
        result = await self._search.fetch()
        return self._process_result(result, return_as=return_as)

    async def first(self, return_as=None):
        """return first instance converted to the target class"""
        result = await self._search.first()
        return self._process_result(result, return_as=return_as)


class ClientProxy:
    def __init__(
        self, _id: str, client: SmartOnFhirClient, fhir_manager: "FhirContextManager"
    ) -> None:
        # id of the resource (Patient, Organisation, Practitioner...)
        self._id = _id
        # let access to the raw fhir api client
        self.client = client
        # add a manager
        self._fhir_manager = fhir_manager
        # allow research stuff
        self._target = self.client.resources(_id)

    def search(self, **kwargs):
        return SearchSet(self._target.search(**kwargs), self._fhir_manager, self.client)

    async def save(
        self,
        resource: Resource | AsyncFHIRResource | CustomFHIRResource,
        **kwargs,
    ):

        resource_to_save = (
            self._fhir_manager.create_async_fhir_resource(
                self.client, resource, **kwargs
            )
            if isinstance(resource, Resource)
            else resource
        )
        await try_(resource_to_save.save)().or_raise(ValueError("Error"))
        return self._fhir_manager.create_async_fhir_resource(self.client, resource_to_save)

    async def update(
        self,
        resource: Resource | AsyncResource | CustomFHIRResource,
        **kwargs: Any,
    ):
        by_alias = kwargs.pop("by_alias")
        resource_to_save = self._fhir_manager.create_async_fhir_resource(
            self.client, resource, **kwargs
        )

        return await try_(resource_to_save.update)(
            **kwargs, by_alias=by_alias
        ).or_raise()

    def upsert(self, resource):
        ...

    async def delete(
        self, resource: Resource | AsyncResource | CustomFHIRResource, **kwargs
    ):
        resource_to_save = self._fhir_manager.create_async_fhir_resource(
            self.client, resource, **kwargs
        )
        return await try_(resource_to_save.delete)().or_raise()


T = TypeVar("T", bound=Resource)


class FhirContextRequester:
    """
    Fhir requester attached to one tenant
    """

    # to be extended
    RESOURCES = frozenset(
        {
            "Patient",
            "Organization",
            "Practitioner",
            "Condition",
            "ResearchStudy",
            "ResearchSubject",
            "Medication",
            "MedicationAdministration",
        }
    )

    def __init__(self, client):
        self._id = client.url.split("/")[-1]
        self._client = client
        self._fhir_manager = client.fhir_manager

        for resource_name in FhirContextRequester.RESOURCES:
            self.__setattr__(
                resource_name, ClientProxy(resource_name, client, self._fhir_manager)
            )

    def _get_result_as_or_raw(
        self, resource: AsyncResource, *, return_as: Type[T] = None
    ) -> CustomFHIRResource | T:
        if return_as:
            return return_as(**resource)
        return self._fhir_manager.create_async_fhir_resource(self._client, resource)

    async def resolve_ref(
        self,
        reference: Union[Reference, str],
        *,
        return_as: Type[T] = None,
        raise_if_none: bool = False,
    ) -> CustomFHIRResource | T | None | NoReturn:
        """resolve a fhir reference"""
        if not reference:
            if raise_if_none:
                raise ValueError("Reference is None")
            return None

        is_fhir_reference = isinstance(reference, Reference)
        if (
            is_fhir_reference
            and reference.reference is None
            and reference.identifier is not None
            and reference.type is not None
        ):
            # handle identifier
            identifier_as_fhir: Identifier = reference.identifier
            result = (
                await self._client.resources(reference.type)
                .search(identifier=identifier_as_fhir.value)
                .first()
            )
            return self._get_result_as_or_raw(result, return_as=return_as)

        if is_fhir_reference and reference.reference is not None:
            reference = reference.reference
        # used for conversion
        fhirpy_resource_dict = await self._client.reference(
            reference=reference
        ).to_resource()
        return self._get_result_as_or_raw(fhirpy_resource_dict, return_as=return_as)



class FhirContextManager:
    """

    main context manager to perform request to the fhir server
    allow handling CRUD operation. This is finally a small wrapper around
    the client API.

    """

    OWN_FHIR_URL = os.getenv("OWN_FHIR_URL", "http://localhost:8080/fhir")

    def __init__(self, own_fhir_url: str | None = None):
        self.OWN_FHIR_URL = own_fhir_url or self.OWN_FHIR_URL
        self.cls_by_partner_id = defaultdict(dict)

    def create_async_fhir_resource(
        self,
        client: SmartOnFhirClient,
        resource: CustomFHIRResource | AsyncResource | Resource,
        **kwargs: Any,
    ) -> CustomFHIRResource | NoReturn:

        partner_name = client.partner_name
        resource_type = resource.resource_type
        wanted_cls = self.cls_by_partner_id[partner_name].get(resource_type)
        cls = wanted_cls or CustomFHIRResource
        match (resource):
            case Resource():
                return cls(
                    self,
                    client,
                    resource.resource_type,
                    **resource.dict(by_alias=kwargs.get("by_alias", False)),
                )
            case AsyncResource():
                return cls(
                    self, client, resource.resourceType, **resource
                )
            case CustomFHIRResource():
                return resource
            case _:
                raise ValueError("Could not create async fhir resource")

    def register_partner(self, partner: Partner, client: SmartOnFhirClient) -> None:
        """Add a partner requester with the partition of the partner"""
        partner_name = partner.name
        self.__setattr__(partner_name, FhirContextRequester(client))
        self.__setattr__(
            f"TARGET_{partner_name}",
            FhirContextRequester(
                SmartOnFhirClient(url=f"{self.OWN_FHIR_URL}/{partner_name}", authorization="", partner=partner, fhir_manager=self)
            ),
        )

    async def register_partner_async(self, builder: SmartOnFhirClientBuilder):
        client = await builder.build(self)
        partner = builder._partner
        partner_name = partner.name
        # register for each resource, its own callback
        for resource_type, cb in builder._cls_by_resource.items():
            self.cls_by_partner_id[partner_name][resource_type] = cb

        self.register_partner(partner, client)

    def get_partner(self, partner_name) -> FhirContextRequester | None:
        partner_requester = getattr(self, partner_name)
        if partner_requester is None:
            warnings.warn(
                f"fhir manager does not have a '{partner_name}' partner registered. Did you registered it ?"
            )
        return partner_requester


# create a singleton of the fhir manager
default_fhir_client_manager = FhirContextManager()
fhir_client_manager = default_fhir_client_manager