from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from memory_agent import auth, control, db
from memory_agent.config import Settings
from memory_agent.errors import ApiError, BadRequest


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        db.init_db(settings.db_path)
        conn = db.connect(settings.db_path)
        try:
            generated_key = auth.bootstrap_admin(conn, settings.admin_key)
        finally:
            conn.close()
        if generated_key:
            print(f"Admin API key (shown once, store it now): {generated_key}", flush=True)
        yield

    app = FastAPI(title="memory-core", lifespan=lifespan)
    app.state.settings = settings
    _install_error_handlers(app)
    app.include_router(control.router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse({"message": exc.message, "type": exc.type}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        parts = []
        for err in exc.errors():
            location = ".".join(str(p) for p in err["loc"][1:])
            parts.append(f"{location}: {err['msg']}" if location else err["msg"])
        body = {"message": "; ".join(parts), "type": BadRequest.type}
        return JSONResponse(body, status_code=400)


app = create_app()
