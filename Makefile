.PHONY: test test-integration generate check

## Run unit tests (fast, no Docker needed)
test:
	python -m pytest tests/ -m "not integration" -q

## Run integration tests against a Docker slskd instance
## Starts Docker, waits for healthy, extracts API key, runs tests, stops Docker.
test-integration:
	docker compose -f docker/docker-compose.yml up -d
	@echo "Waiting for slskd to become healthy..."
	@API_KEY=$$(bash docker/wait-for-ready.sh 2>/dev/null | grep "API Key:" | awk '{print $$NF}') && \
		export SLSKD_URL=http://localhost:15030 && \
		export SLSKD_API_KEY=$$API_KEY && \
		echo "Running integration tests with API key: $$API_KEY" && \
		python -m pytest tests/test_integration.py -v; \
		EXIT_CODE=$$?; \
		docker compose -f docker/docker-compose.yml down; \
		exit $$EXIT_CODE

## Regenerate generated/server.py from the OpenAPI spec
generate:
	python -m generator

## Run nix flake check (unit tests inside Nix sandbox)
check:
	nix flake check
