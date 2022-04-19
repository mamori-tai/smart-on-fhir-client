# smart-on-fhir-client 🔥

Package allowing to request a fhir server with the smart-on-fhir protocol. 

> ℹ Warning
>
> It is not a webserver providing a webserver with a callback url
> usually involved in the smart-on-fhir procedure


### Tutorial

First, we will need to create a partner. We can do this easily subclassing the `Partner` class.
```python
import os
from smart_on_fhir_client.partner import Partner
from typing import Set
from smart_on_fhir_client.strategy import Strategy

class Lifen(Partner):
    name = 'LIFEN'
    supported_strategies: Set[Strategy] = {Strategy.M2M}
    client_id: str = os.getenv("LIFEN_CLIENT_ID")
    client_secret: str = os.getenv("LIFEN_CLIENT_SECRET")
    token_url: str = ... # set the token url
    fhir_url: str = ... # set the fhir url

    # additional information
    audience: str = ... # audience
    database_reference: str = ... # optional 
    grant_type: str = "client_credentials" # set the credentials

LIFEN = Lifen()
```

```python
from smart_on_fhir_client.client import smart_client_factory
from smart_on_fhir_client.requester.fhir_requester import fhir_client_manager
from smart_on_fhir_client.strategy import Strategy

# set up your own fhir server url
fhir_client_manager.set_own_fhir_url("http://localhost:8080/fhir")

async def register():
    async with smart_client_factory:
        await fhir_client_manager.register_partner_async(
            smart_client_factory.builder()
                .for_partner(LIFEN)
                .for_strategy(Strategy.M2M)
                # you can register special classes for specific fhir resources
                .register_cls_for('Patient', LifenPatientResource)
        )
        first_patient = await fhir_client_manager.LIFEN.Patient.search().limit(10).first()
        await first_patient.pipe_to_target_fhir_server()

```


### Features

Allow to send some fetched fhir resources to another fhir server
via the `pipe_to_target_fhir_server`, making data transfer between two fhir
servers easier.

### Notes
Work based heavily on fhir-py and fhir-resources python packages