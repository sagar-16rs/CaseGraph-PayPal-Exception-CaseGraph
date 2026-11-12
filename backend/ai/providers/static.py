from __future__ import annotations

from copy import deepcopy


class StaticReasoningProvider:
    provider_name = "static"
    model_name = "static"

    def __init__(self, output):
        self.output = output

    async def run(self, bundle):
        # Tests and local demos use this provider. Return a copy so validation or
        # callers cannot mutate the fixture stored on the provider instance.
        return deepcopy(self.output), {
            "provider": self.provider_name,
            "model": self.model_name,
            "response_id": "static",
        }
