.PHONY: backend frontend pipeline reset inspect previews convert conversion-quality test check

backend:
	uv run --locked python app.py

frontend:
	npm --prefix frontend run dev

pipeline:
	uv run --locked python -m backend.app.pipeline.ingest

reset:
	uv run --locked python -m backend.app.pipeline.ingest --reset

inspect:
	uv run --locked python scripts/inspect_dataset.py

previews:
	uv run --locked python scripts/verify_previews.py

convert:
	uv run --locked python scripts/convert_all.py

conversion-quality:
	uv run --locked python scripts/report_conversion_quality.py

test:
	uv run --locked python -m unittest discover -s backend/tests -v
	npm --prefix frontend run check

check: pipeline test
