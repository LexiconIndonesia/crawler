.PHONY: help install install-dev run run-prod test lint format type-check clean docker-build docker-up docker-down docker-logs db-up db-down db-shell redis-shell nats-shell monitoring-up monitoring-down setup dev encode-gcs playwright install-hooks partition-create partition-drop partition-maintain partition-list sqlc-generate regenerate-schema db-migrate db-migrate-check db-migrate-current db-migrate-history db-migrate-create db-migrate-rollback db-migrate-rollback-to db-stamp db-stamp-revision

# Default target
.DEFAULT_GOAL := help

# Variables
PYTHON := uv run python
PYTEST := uv run pytest
UVICORN := uv run uvicorn
RUFF := uv run ruff
MYPY := uv run mypy
DOCKER_COMPOSE := docker-compose

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

##@ Help

help: ## Display this help message
	@echo "$(BLUE)Lexicon Crawler - Available Commands$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf ""} /^[a-zA-Z_-]+:.*?##/ { printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(YELLOW)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Setup

install: ## Install production dependencies
	@echo "$(BLUE)📦 Installing production dependencies...$(NC)"
	uv sync --no-dev
	@echo "$(GREEN)✅ Dependencies installed$(NC)"

install-dev: ## Install development dependencies
	@echo "$(BLUE)📦 Installing development dependencies...$(NC)"
	uv sync
	@echo "$(GREEN)✅ Dev dependencies installed$(NC)"

playwright: ## Install Playwright browsers
	@echo "$(BLUE)🎭 Installing Playwright browsers...$(NC)"
	$(PYTHON) -m playwright install chromium
	@echo "$(GREEN)✅ Playwright browsers installed$(NC)"

install-hooks: ## Install pre-commit hooks
	@echo "$(BLUE)🪝 Installing pre-commit hooks...$(NC)"
	uv run pre-commit install
	@echo "$(GREEN)✅ Pre-commit hooks installed$(NC)"
	@echo "$(YELLOW)💡 Hooks will run automatically on git commit$(NC)"
	@echo "$(YELLOW)💡 Run 'pre-commit run --all-files' to check all files$(NC)"

setup: ## Complete project setup (install deps + playwright + hooks + create .env)
	@echo "$(BLUE)🚀 Setting up Lexicon Crawler...$(NC)"
	@if [ ! -f .env ]; then \
		echo "$(YELLOW)📝 Creating .env from template...$(NC)"; \
		cp .env.example .env; \
		echo "$(YELLOW)⚠️  Please update .env with your configuration$(NC)"; \
	fi
	@make install-dev
	@make playwright
	@make install-hooks
	@echo "$(GREEN)✅ Setup complete!$(NC)"

##@ Development

dev: db-up ## Start development server with auto-reload
	@echo "$(BLUE)🚀 Starting development server...$(NC)"
	@echo "$(YELLOW)📊 API Docs: http://localhost:8000/docs$(NC)"
	$(UVICORN) main:app --reload --host 0.0.0.0 --port 8000

dev-all: db-up ## Start development server + worker together
	@echo "$(BLUE)🚀 Starting API server and worker...$(NC)"
	@echo "$(YELLOW)📊 API Docs: http://localhost:8000/docs$(NC)"
	@echo "$(YELLOW)⚙️  Press Ctrl+C to stop all processes$(NC)"
	@trap 'kill 0' INT TERM; \
	$(UVICORN) main:app --reload --host 0.0.0.0 --port 8000 & \
	$(PYTHON) -m crawler.worker & \
	wait

dev-worker: db-up ## Start worker only (for queue processing)
	@echo "$(BLUE)⚙️  Starting worker...$(NC)"
	$(PYTHON) -m crawler.worker

run: ## Run production server
	@echo "$(BLUE)🚀 Starting production server...$(NC)"
	$(UVICORN) main:app --host 0.0.0.0 --port 8000

run-prod: ## Run production server with multiple workers
	@echo "$(BLUE)🚀 Starting production server (4 workers)...$(NC)"
	$(UVICORN) main:app --host 0.0.0.0 --port 8000 --workers 4

##@ Testing

test: ## Run all tests
	@echo "$(BLUE)🧪 Running tests...$(NC)"
	$(PYTEST)

test-unit: ## Run unit tests only
	@echo "$(BLUE)🧪 Running unit tests...$(NC)"
	$(PYTEST) tests/unit/

test-integration: ## Run integration tests only
	@echo "$(BLUE)🧪 Running integration tests...$(NC)"
	$(PYTEST) tests/integration/

test-cov: ## Run tests with coverage report
	@echo "$(BLUE)🧪 Running tests with coverage...$(NC)"
	$(PYTEST) --cov=crawler --cov-report=html --cov-report=term
	@echo "$(GREEN)📊 Coverage report: htmlcov/index.html$(NC)"

test-watch: ## Run tests in watch mode
	@echo "$(BLUE)🧪 Running tests in watch mode...$(NC)"
	$(PYTEST) -f

##@ Code Quality

lint: ## Run linter
	@echo "$(BLUE)🔍 Running linter...$(NC)"
	$(RUFF) check .

lint-fix: ## Run linter with auto-fix
	@echo "$(BLUE)🔧 Running linter with auto-fix...$(NC)"
	$(RUFF) check --fix .

format: ## Format code
	@echo "$(BLUE)✨ Formatting code...$(NC)"
	$(RUFF) format .

format-check: ## Check code formatting
	@echo "$(BLUE)🔍 Checking code formatting...$(NC)"
	$(RUFF) format --check .

type-check: ## Run type checker
	@echo "$(BLUE)🔍 Running type checker...$(NC)"
	$(MYPY) crawler/

check: format lint type-check ## Run all code quality checks
	@echo "$(GREEN)✅ All checks passed$(NC)"

##@ Docker

docker-build: ## Build Docker image
	@echo "$(BLUE)🐳 Building Docker image...$(NC)"
	docker build -t lexicon-crawler:latest .

docker-up: ## Start all services with Docker Compose
	@echo "$(BLUE)🐳 Starting all services...$(NC)"
	$(DOCKER_COMPOSE) up -d
	@echo "$(GREEN)✅ Services started$(NC)"
	@make docker-status

docker-down: ## Stop all services
	@echo "$(BLUE)🛑 Stopping all services...$(NC)"
	$(DOCKER_COMPOSE) down

docker-down-v: ## Stop all services and remove volumes
	@echo "$(RED)🛑 Stopping services and removing volumes...$(NC)"
	$(DOCKER_COMPOSE) down -v

docker-logs: ## View logs from all services
	$(DOCKER_COMPOSE) logs -f

docker-status: ## Show status of all services
	@echo "$(BLUE)📊 Service Status:$(NC)"
	@$(DOCKER_COMPOSE) ps

docker-restart: docker-down docker-up ## Restart all services

##@ Database

db-up: ## Start PostgreSQL and Redis
	@echo "$(BLUE)🗄️  Starting database services...$(NC)"
	$(DOCKER_COMPOSE) up -d postgres redis nats
	@echo "$(YELLOW)⏳ Waiting for services to be ready...$(NC)"
	@sleep 5
	@echo "$(GREEN)✅ Database services ready$(NC)"

db-down: ## Stop database services
	@echo "$(BLUE)🛑 Stopping database services...$(NC)"
	$(DOCKER_COMPOSE) stop postgres redis nats

db-shell: ## Connect to PostgreSQL shell
	@echo "$(BLUE)🗄️  Connecting to PostgreSQL...$(NC)"
	$(DOCKER_COMPOSE) exec postgres psql -U crawler -d crawler

redis-shell: ## Connect to Redis shell
	@echo "$(BLUE)🔴 Connecting to Redis...$(NC)"
	$(DOCKER_COMPOSE) exec redis redis-cli

nats-shell: ## Open NATS monitoring
	@echo "$(BLUE)📡 NATS Monitoring: http://localhost:8222$(NC)"
	@open http://localhost:8222 || xdg-open http://localhost:8222 || echo "Open http://localhost:8222 in your browser"

##@ Database Migrations (Alembic)

db-migrate: ## Apply database migrations with Alembic
	@echo "$(BLUE)🔄 Running database migrations with Alembic...$(NC)"
	uv run alembic upgrade head
	@echo "$(GREEN)✅ Migrations applied$(NC)"

db-migrate-check: ## Check if database is up to date
	@echo "$(BLUE)🔍 Checking migration status...$(NC)"
	@uv run alembic current -v || echo "$(YELLOW)⚠️  Database not stamped or migrations pending$(NC)"

db-migrate-current: ## Show current migration version
	@echo "$(BLUE)📍 Current migration:$(NC)"
	@uv run alembic current

db-migrate-history: ## Show migration history
	@echo "$(BLUE)📜 Migration history:$(NC)"
	@uv run alembic history

db-migrate-create: ## Create a new migration (usage: make db-migrate-create MSG="description")
	@if [ -z "$(MSG)" ]; then \
		echo "$(RED)❌ Error: MSG not set$(NC)"; \
		echo "$(YELLOW)Usage: make db-migrate-create MSG='your migration description'$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)📝 Creating new migration: $(MSG)$(NC)"
	@uv run alembic revision -m "$(MSG)"
	@echo "$(GREEN)✅ Migration created in alembic/versions/$(NC)"
	@echo "$(YELLOW)⚠️  Don't forget to implement upgrade() and downgrade() functions!$(NC)"

db-migrate-rollback: ## Rollback one migration
	@echo "$(YELLOW)⬇️  Rolling back one migration...$(NC)"
	@uv run alembic downgrade -1
	@echo "$(YELLOW)⚠️  Migration rolled back$(NC)"

db-migrate-rollback-to: ## Rollback to specific revision (usage: make db-migrate-rollback-to REV=<revision>)
	@if [ -z "$(REV)" ]; then \
		echo "$(RED)❌ Error: REV not set$(NC)"; \
		echo "$(YELLOW)Usage: make db-migrate-rollback-to REV=<revision_id>$(NC)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)⬇️  Rolling back to revision $(REV)...$(NC)"
	@uv run alembic downgrade $(REV)
	@echo "$(YELLOW)⚠️  Rolled back to $(REV)$(NC)"

db-stamp: ## Stamp database with head revision (USE WITH CAUTION)
	@echo "$(YELLOW)⚠️  Stamping database with head revision...$(NC)"
	@uv run alembic stamp head
	@echo "$(GREEN)✅ Database stamped$(NC)"

db-stamp-revision: ## Stamp database with specific revision (usage: make db-stamp-revision REV=<revision>)
	@if [ -z "$(REV)" ]; then \
		echo "$(RED)❌ Error: REV not set$(NC)"; \
		echo "$(YELLOW)Usage: make db-stamp-revision REV=<revision_id>$(NC)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)⚠️  Stamping database with revision $(REV)...$(NC)"
	@uv run alembic stamp $(REV)
	@echo "$(GREEN)✅ Database stamped with $(REV)$(NC)"

##@ Database Tools

sqlc-generate: ## Generate type-safe Python code from SQL queries
	@echo "$(BLUE)⚙️  Generating code with sqlc...$(NC)"
	sqlc generate
	@echo "$(GREEN)✅ Code generated in crawler/db/generated/$(NC)"

regenerate-schema: ## Regenerate schema from database (after migrations)
	@echo "$(BLUE)⚙️  Regenerating schema from database...$(NC)"
	@docker exec lexicon-postgres pg_dump --schema-only --no-owner --no-privileges --no-tablespaces -U crawler crawler > sql/schema/current_schema.sql
	@sed -i '' '1,21d' sql/schema/current_schema.sql
	@sed -i '' '/^\\unrestrict/d' sql/schema/current_schema.sql
	@sed -i '' '/^\\restrict/d' sql/schema/current_schema.sql
	@sed -i '' 's/public\.//g' sql/schema/current_schema.sql
	@python3 -c "import re; content = open('sql/schema/current_schema.sql').read(); patterns = [r'-- Name: create_crawl_log_partition.*?(?=-- Name: [a-z])', r'-- Name: create_future_crawl_log_partitions.*?(?=-- Name: [a-z])', r'-- Name: drop_old_crawl_log_partitions.*?(?=-- Name: [a-z])', r'-- Name: crawl_log_partitions; Type: VIEW.*?(?=-- Name: [a-z])']; [content := re.sub(p, '', content, flags=re.DOTALL) for p in patterns]; open('sql/schema/current_schema.sql', 'w').write(content)"
	@echo "$(GREEN)✅ Schema regenerated$(NC)"

partition-create: ## Create future log partitions
	@echo "$(BLUE)📅 Creating future log partitions...$(NC)"
	$(PYTHON) scripts/maintain_partitions.py create-future
	@echo "$(GREEN)✅ Partitions created$(NC)"

partition-drop: ## Drop old log partitions based on retention policy
	@echo "$(BLUE)🗑️  Dropping old log partitions...$(NC)"
	$(PYTHON) scripts/maintain_partitions.py drop-old
	@echo "$(GREEN)✅ Old partitions dropped$(NC)"

partition-maintain: ## Maintain log partitions (create future + drop old)
	@echo "$(BLUE)🔧 Maintaining log partitions...$(NC)"
	$(PYTHON) scripts/maintain_partitions.py maintain

partition-list: ## List all log partitions with metadata
	@echo "$(BLUE)📋 Listing log partitions...$(NC)"
	$(PYTHON) scripts/maintain_partitions.py list

##@ Monitoring

monitoring-up: ## Start monitoring stack (Prometheus, Grafana, Loki)
	@echo "$(BLUE)📊 Starting monitoring stack...$(NC)"
	$(DOCKER_COMPOSE) up -d prometheus grafana loki promtail alertmanager
	@echo "$(YELLOW)⏳ Waiting for services to start...$(NC)"
	@sleep 10
	@echo "$(GREEN)✅ Monitoring stack started!$(NC)"
	@echo ""
	@echo "$(YELLOW)Available dashboards:$(NC)"
	@echo "  • Grafana:      http://localhost:3000 (admin/admin)"
	@echo "  • Prometheus:   http://localhost:9090"
	@echo "  • AlertManager: http://localhost:9093"

monitoring-down: ## Stop monitoring stack
	@echo "$(BLUE)🛑 Stopping monitoring stack...$(NC)"
	$(DOCKER_COMPOSE) stop prometheus grafana loki promtail alertmanager

##@ Utilities

encode-gcs: ## Encode GCS credentials to base64 (usage: make encode-gcs FILE=path/to/credentials.json)
	@if [ -z "$(FILE)" ]; then \
		echo "$(RED)❌ Error: FILE parameter required$(NC)"; \
		echo "$(YELLOW)Usage: make encode-gcs FILE=path/to/credentials.json$(NC)"; \
		exit 1; \
	fi
	@if [ ! -f "$(FILE)" ]; then \
		echo "$(RED)❌ Error: File '$(FILE)' not found$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)🔐 Encoding GCS credentials...$(NC)"
	@if [ "$$(uname)" = "Darwin" ]; then \
		BASE64=$$(base64 -i "$(FILE)"); \
	else \
		BASE64=$$(base64 -w 0 "$(FILE)"); \
	fi; \
	echo "$(GREEN)✅ Base64-encoded credentials:$(NC)"; \
	echo "$$BASE64"; \
	echo ""; \
	echo "$(YELLOW)Add this to your .env file:$(NC)"; \
	echo "GOOGLE_APPLICATION_CREDENTIALS_BASE64=$$BASE64"

clean: ## Clean up temporary files and caches
	@echo "$(BLUE)🧹 Cleaning up...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name "*.log" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage 2>/dev/null || true
	@echo "$(GREEN)✅ Cleanup complete$(NC)"

logs: ## Create logs directory
	@mkdir -p logs

##@ Information

info: ## Display project information
	@echo "$(BLUE)Lexicon Crawler - Project Information$(NC)"
	@echo ""
	@echo "$(YELLOW)Python Version:$(NC)"
	@cat .python-version
	@echo ""
	@echo "$(YELLOW)Installed Packages:$(NC)"
	@uv pip list | head -20
	@echo ""
	@echo "$(YELLOW)Docker Services:$(NC)"
	@$(DOCKER_COMPOSE) ps 2>/dev/null || echo "  No services running"

urls: ## Display all service URLs
	@echo "$(BLUE)📡 Service URLs:$(NC)"
	@echo ""
	@echo "$(YELLOW)Application:$(NC)"
	@echo "  • API:          http://localhost:8000"
	@echo "  • Docs:         http://localhost:8000/docs"
	@echo "  • ReDoc:        http://localhost:8000/redoc"
	@echo "  • Health:       http://localhost:8000/health"
	@echo "  • Metrics:      http://localhost:8000/metrics"
	@echo ""
	@echo "$(YELLOW)Infrastructure:$(NC)"
	@echo "  • PostgreSQL:   localhost:5432"
	@echo "  • Redis:        localhost:6379"
	@echo "  • NATS:         localhost:4222"
	@echo "  • NATS Monitor: http://localhost:8222"
	@echo ""
	@echo "$(YELLOW)Monitoring:$(NC)"
	@echo "  • Grafana:      http://localhost:3000 (admin/admin)"
	@echo "  • Prometheus:   http://localhost:9090"
	@echo "  • AlertManager: http://localhost:9093"

##@ OpenAPI Code Generation

validate-openapi: ## Validate OpenAPI specification
	@echo "$(BLUE)✅ Validating OpenAPI spec...$(NC)"
	openapi-generator-cli validate -i openapi.yaml 2>&1 | grep -v "Unable to query repository" | head -5
	@echo "$(GREEN)✅ OpenAPI spec is valid$(NC)"

generate-models: ## Generate Pydantic models from OpenAPI spec
	@echo "$(BLUE)⚙️  Generating Pydantic models from OpenAPI spec...$(NC)"
	@mkdir -p crawler/api/generated
	uv run datamodel-codegen \
	  --input openapi.yaml \
	  --output crawler/api/generated/models.py \
	  --input-file-type openapi \
	  --output-model-type pydantic_v2.BaseModel \
	  --use-standard-collections \
	  --use-schema-description \
	  --field-constraints \
	  --use-default \
	  --use-annotated \
	  --use-double-quotes \
	  --target-python-version 3.14
	@echo "$(GREEN)✅ Pydantic models generated$(NC)"
	@echo "$(YELLOW)⚠️  Remember to review crawler/api/generated/extended.py for any needed updates$(NC)"

generate-client: ## Generate Python client SDK from OpenAPI spec
	@echo "$(BLUE)⚙️  Generating Python client SDK...$(NC)"
	@mkdir -p clients
	openapi-generator-cli generate \
	  -i openapi.yaml \
	  -g python \
	  -o clients/python \
	  --additional-properties=packageName=lexicon_crawler_client,packageVersion=1.0.0,projectName=lexicon-crawler-client
	@echo "$(GREEN)✅ Python client SDK generated in clients/python/$(NC)"

generate-all: validate-openapi generate-models generate-client ## Validate and generate all OpenAPI artifacts
	@echo "$(GREEN)✅ All OpenAPI artifacts generated successfully$(NC)"
