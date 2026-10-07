from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()
ASSETS = Path(__file__).parent / "recovery_assets"
HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; connect-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'",
}


@router.get("/password-reset", include_in_schema=False)
def page():
    return FileResponse(ASSETS / "index.html", media_type="text/html", headers=HEADERS)


@router.get("/password-reset.js", include_in_schema=False)
def script():
    return FileResponse(ASSETS / "reset.js", media_type="application/javascript", headers=HEADERS)
