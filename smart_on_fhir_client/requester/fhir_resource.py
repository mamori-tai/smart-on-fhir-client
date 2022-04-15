from fhirpy.lib import AsyncFHIRResource

from smart_on_fhir_client.requester.mixin import SerializeMixin


class CustomFHIRResource(SerializeMixin, AsyncFHIRResource):
    def __init__(self, manager, client, resource_type, **kwargs):
        super().__init__(client, resource_type, **kwargs)
        self.fhir_client_manager = manager

    @property
    def partition_id(self):
        return self.client.partner_name

    @property
    def requester(self):
        return getattr(
            self.fhir_client_manager, f"TARGET_{self.partition_id}"
        )

    async def find_by_identifier(self, identifier_url: str, client_proxy):
        identifier_value = self.get_by_path([
            'identifier',
            {'system': identifier_url},
            'value'
        ])
        resource = await client_proxy.search(identifier=identifier_value).first()
        return resource.id if resource is not None else None

    async def pipe_to_target_fhir_server(self, identifier_url:str = None):
        client_proxy = getattr(self.requester, self.resource_type)
        resource_id = await self.find_by_identifier(identifier_url, client_proxy)
        to_delete = {"fhir_client_manager"}

        if resource_id is None:
            to_delete.add("id")

        data = {**self}

        for attr in to_delete:
            data.pop(attr, None)

        return await client_proxy.save(
            client_proxy.client.resource(self.resource_type, **data)
        )

    def __str__(self):
        return "<{0} {1}>".format("CustomFHIRResource", self._get_path())
