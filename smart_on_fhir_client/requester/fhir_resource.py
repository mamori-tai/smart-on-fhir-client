from fhirpy.lib import AsyncFHIRResource
from loguru import logger

from smart_on_fhir_client.requester.mixin import SerializeMixin


class CustomFHIRResource(SerializeMixin, AsyncFHIRResource):
    def __init__(self, manager, client, resource_type, **kwargs):
        super().__init__(client, resource_type, **kwargs)
        self.fhir_client_manager = manager

    @property
    def partition_id(self):
        return self.client.client_name

    @property
    def source_requester(self):
        return getattr(self.fhir_client_manager, self.partition_id)

    @property
    def target_requester(self):
        logger.debug("partition id: {}", self.partition_id)
        return getattr(self.fhir_client_manager, f"TARGET_{self.partition_id}")

    async def find_by_identifier(self, target_identifier_url: str, client_proxy):
        identifier_value = self.get_by_path(
            ["identifier", {"system": target_identifier_url}, "value"]
        )
        if identifier_value is None:
            return None

        resource = await client_proxy.search(identifier=identifier_value).first()
        return resource.id if resource is not None else None

    async def pipe_to_target_fhir_server(self, target_identifier_url: str = None):
        client_proxy = getattr(self.target_requester, self.resource_type)
        # try to find the resource on the target fhir server
        resource_id = await self.find_by_identifier(target_identifier_url, client_proxy)

        data = self.serialize()

        # if not found on the target server fhir, we pop the id
        # allowing a post instead of a put
        if resource_id is None:
            data.pop("id", None)
        else:
            # resource has been found on the target server fhir
            # so setting the id of the target resource
            data["id"] = resource_id

        # finally save or update based on presence / absence of id attribute
        return await client_proxy.save(
            client_proxy.client.resource(self.resource_type, **data)
        )

    def __str__(self):
        return "<{0} {1}>".format("CustomFHIRResource", self._get_path())
