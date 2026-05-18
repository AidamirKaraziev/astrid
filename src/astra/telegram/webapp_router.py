from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["telegram-webapp"])

_STATIC = Path(__file__).resolve().parent / "static" / "location_webapp.html"


@router.get("/telegram/webapp/location", response_class=HTMLResponse)
async def location_webapp_page() -> HTMLResponse:
    return HTMLResponse(
        content=_STATIC.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store"},
    )
