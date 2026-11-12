from __future__ import annotations

from fastapi import FastAPI

from backend.security.config import security_config
from backend.security.middleware import SecurityGatewayMiddleware
from backend.security.router import router as auth_router


def install_security(app: FastAPI) -> None:
    errors = security_config.validate()
    if security_config.production and errors:
        raise RuntimeError("security production security configuration is invalid: " + "; ".join(errors))
    app.include_router(auth_router)
    # Upload routes are imported lazily so local environments without
    # python-multipart can still run security-only static checks.
    try:
        from backend.uploads.api import router as uploads_router

        app.include_router(uploads_router)
    except RuntimeError:
        if security_config.production:
            raise
    app.add_middleware(SecurityGatewayMiddleware, config=security_config)

    if security_config.otel_enabled:
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider = TracerProvider(resource=Resource.create({"service.name": "casegraph-api"}))
            exporter = OTLPSpanExporter(endpoint=security_config.otel_endpoint or None)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            FastAPIInstrumentor.instrument_app(app, excluded_urls="health")
        except Exception as exc:
            if security_config.production:
                raise RuntimeError("OTel was requested but trace export/instrumentation could not be initialized") from exc
