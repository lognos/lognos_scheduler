.PHONY: frontend backend sch_fe sch_be help

# Default target
help:
	@echo "Available commands:"
	@echo "  make frontend - Start the frontend (Next.js on port 3900)"
	@echo "  make backend  - Start the backend (FastAPI with uvicorn)"

frontend: sch_fe

backend: sch_be

# Start frontend
sch_fe:
	@echo "Starting frontend on http://localhost:3900..."
	cd frontend && npm run dev

# Start backend
sch_be:
	@echo "Starting backend on http://localhost:8500..."
	source .venv/bin/activate && uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8500
