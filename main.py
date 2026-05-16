"""Точка входа для IDE. Предпочтительно: uv run uvicorn astra.main:app --app-dir src"""

from astra.main import run

if __name__ == "__main__":
    run()
