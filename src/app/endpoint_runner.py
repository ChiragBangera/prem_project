from app.endpoint_manifest import get_endpoint_spec
from app.stat_data import UnderstatData


class EndpointRunner:
    def __init__(self, client=None):
        self.client = client or UnderstatData()
        self._owns_client = client is None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def run(self, endpoint_name: str, **params):
        endpoint_spec = get_endpoint_spec(endpoint_name)
        missing_params = [
            parameter
            for parameter in endpoint_spec.required_params
            if parameter not in params
        ]

        if missing_params:
            missing = ", ".join(missing_params)
            raise ValueError(
                f"Missing required params for '{endpoint_name}': {missing}"
            )

        method = getattr(self.client, endpoint_spec.method_name)
        return await method(**params)

    async def close(self):
        if self._owns_client:
            await self.client.close()
