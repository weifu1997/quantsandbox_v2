.PHONY: test dev run

dev:
	uvicorn app.main:app --reload

run:
	uvicorn app.main:app --host 127.0.0.1 --port 8000

test:
	bash scripts/test.sh
