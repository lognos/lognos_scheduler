.PHONY: frontend backend sch_fe sch_be help

# Default target
help:
	@echo "Available commands:"
	@echo "  make frontend - Start sch_frontend (Next.js on port 3900)"
	@echo "  make backend  - Start sch_backend (FastAPI with uvicorn)"

frontend: sch_fe

backend: sch_be

# Start frontend
sch_fe:
	@echo "Starting sch_frontend on http://localhost:3900..."
	cd sch_frontend && npm run dev

# Start backend
sch_be:
	@echo "Starting sch_backend on http://localhost:8500..."
	source .venv/bin/activate && uvicorn sch_backend.api.main:app --reload --host 0.0.0.0 --port 8500
