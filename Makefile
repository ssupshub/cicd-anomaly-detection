.PHONY: help install demo test api scheduler docker-up docker-down clean

help:
	@echo "CI/CD Anomaly Detection System - Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install      Install dependencies"
	@echo "  make demo         Run quick demo with mock data"
	@echo ""
	@echo "Running:"
	@echo "  make api          Start API server"
	@echo "  make scheduler    Start automated scheduler"
	@echo "  make docker-up    Start all services with Docker"
	@echo "  make docker-down  Stop Docker services"
	@echo ""
	@echo "Testing:"
	@echo "  make test         Run all tests"
	@echo "  make test-ml      Test ML components"
	@echo "  make test-api     Test API endpoints"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean        Clean generated files"
	@echo "  make logs         View Docker logs"

install:
	pip install -r requirements.txt
	@echo "✅ Dependencies installed"
	@echo "📝 Next: Copy .env.template to .env and configure"

demo:
	python demo.py

test:
	pytest tests/ -v

test-ml:
	pytest tests/test_anomaly_detector.py -v

api:
	python api/app.py

scheduler:
	python scheduler.py

docker-up:
	docker-compose up -d
	@echo "✅ Services started"
	@echo "📊 Grafana: http://localhost:3000 (admin/admin)"
	@echo "🔍 Prometheus: http://localhost:9090"
	@echo "🚀 API: http://localhost:5000"

docker-down:
	docker-compose down

docker-build:
	docker-compose build

logs:
	docker-compose logs -f

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.log" -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	@echo "✅ Cleaned up generated files"

setup-env:
	@if [ ! -f .env ]; then \
		cp .env.template .env; \
		echo "✅ Created .env file"; \
		echo "📝 Please edit .env with your credentials"; \
	else \
		echo "⚠️  .env already exists"; \
	fi
