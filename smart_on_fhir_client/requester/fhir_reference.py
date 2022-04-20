from fhirpy.base.exceptions import ResourceNotFound
from fhirpy.lib import AsyncFHIRReference

from smart_on_fhir_client.requester.mixin import SerializeMixin


class CustomFHIRReference(SerializeMixin, AsyncFHIRReference):
    def __init__(self, fhir_manager, client, **kwargs):
        self.client = client
        self.fhir_client_manager = fhir_manager
        super().__init__(self.client, **kwargs)

    async def to_resource(self):
        """
        Returns Resource instance for this reference
        from fhir server otherwise.
        """
        if not self.is_local:
            raise ResourceNotFound("Can not resolve not local resource")
        resource = (
            await self.client.resources(self.resource_type).search(_id=self.id).get()
        )
        return self.fhir_client_manager.create_async_fhir_resource(
            self.client, resource
        )

    def __str__(self):  # pragma: no cover
        return f"<CustomFHIRReference {self.reference}>"
