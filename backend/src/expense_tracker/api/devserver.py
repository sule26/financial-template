"""Dev server entrypoint for ``uvicorn --reload`` (``task dev``)."""

from expense_tracker.api.app import create_app

app = create_app()
