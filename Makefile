.PHONY: backend-format backend-lint backend-typecheck backend-test mobile-install mobile-lint mobile-typecheck mobile-test docker-config docker-build docker-up docker-ps

backend-format:
	cd backend && black .

backend-lint:
	cd backend && ruff check .

backend-typecheck:
	cd backend && mypy app

backend-test:
	cd backend && pytest

mobile-install:
	cd mobile && npm install

mobile-lint:
	cd mobile && npm run lint

mobile-typecheck:
	cd mobile && npm run typecheck

mobile-test:
	cd mobile && npm test -- --runInBand

docker-config:
	docker compose config

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-ps:
	docker compose ps
