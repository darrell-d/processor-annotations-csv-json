.PHONY: help run clean test

SERVICE_NAME ?= processor-annotations-csv-json

.DEFAULT: help

help:
	@echo "Make Help for $(SERVICE_NAME)"
	@echo ""
	@echo "make run   - build and run the processor via docker-compose"
	@echo "make local - run against data/input without docker"
	@echo "make clean - remove output files"
	@echo "make test  - run the unit test suite"

run:
	docker-compose down --remove-orphans
	docker-compose build
	docker-compose up --exit-code-from processor

local:
	INPUT_DIR=data/input OUTPUT_DIR=data/output python3 -m processor.main

clean:
	rm -rf data/output/*

test:
	python3 -m pytest tests/ -q
