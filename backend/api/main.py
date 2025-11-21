from fastapi import FastAPI
import logfire
from backend.api.routers import chat
from backend.config.settings import settings

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

# Configure Logfire
if settings.LOGFIRE_TOKEN:
    logfire.configure(token=settings.LOGFIRE_TOKEN)
    logfire.instrument_fastapi(app)
    logfire.instrument_pydantic()

# Include Routers
app.include_router(chat.router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
