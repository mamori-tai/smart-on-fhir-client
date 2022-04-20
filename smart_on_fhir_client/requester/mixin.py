from smart_on_fhir_client.utils import mixin


@mixin
class SerializeMixin:
    def serialize(self):
        resource_as_json = super().serialize()
        resource_as_json.pop("fhir_client_manager", None)
        resource_as_json.pop("_fhir_manager", None)
        return resource_as_json
