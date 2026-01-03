.PHONY: p6 backend help

# Default target
help:
	@echo "Available commands:"
	@echo "  make p6      - Start the frontend (Next.js on port 3900)"
	@echo "  make backend - Start the backend (FastAPI with uvicorn)"

# Start frontend
p6:
	@echo "Starting frontend on http://localhost:3900..."
	cd frontend && npm run dev

# Start backend
backend:
	@echo "Starting backend on http://localhost:8500..."
	source venv/bin/activate && uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8500
