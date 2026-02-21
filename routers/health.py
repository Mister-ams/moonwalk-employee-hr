from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
