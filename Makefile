.PHONY: install test lint clean build release

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

lint:
	black src/
	ruff check src/

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build: clean
	python -m build

release: build
	@echo "Tag and push: git tag vX.X.X && git push origin --tags"
