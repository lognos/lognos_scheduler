from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logfire

from backend.api.routers import chat, conversations, p6_schedules, projects
from backend.config.settings import settings

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

# CORS configuration for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3900",  # Next.js dev server
        "http://localhost:3001",
        "http://127.0.0.1:3900",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Configure Logfire
if settings.LOGFIRE_TOKEN:
    logfire.configure(token=settings.LOGFIRE_TOKEN)
    logfire.instrument_fastapi(app)
    logfire.instrument_pydantic()

# Include Routers
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(conversations.router, prefix="/api/v1/conversations", tags=["conversations"])
app.include_router(p6_schedules.router, prefix="/api/v1/p6-schedules", tags=["p6-schedules"])
app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/api/v1/health")
async def api_health_check():
    return {"status": "ok", "service": "scheduling-assistant"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
