"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.intel import router as intel_router
from app.services.errors import DomainError

app = FastAPI(
    title="Intel Approval Flow (S5-INTEL-027)",
    description=(
        "Supervisor approval flow and state machine for intel items. "
        "Identity/role headers are an S2-IAM stub for isolated testing only."
    ),
    version="1.0.0",
)

app.include_router(intel_router)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content={"detail": exc.message, "code": exc.code, **({"extra": exc.detail} if exc.detail else {})},
    )