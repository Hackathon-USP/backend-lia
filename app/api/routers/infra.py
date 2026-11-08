from fastapi import APIRouter

router = APIRouter(tags=["infra"])


@router.get("/saude")
def saude():
    return {"status": "ok"}
