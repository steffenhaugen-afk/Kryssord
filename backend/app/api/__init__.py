from fastapi import APIRouter

from .kryssord import router as kryssord_router
from .ord import router as ord_router

api_router = APIRouter()
api_router.include_router(ord_router)
api_router.include_router(kryssord_router)
