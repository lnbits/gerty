from fastapi import APIRouter

from .crud import db
from .views import gerty_generic_router
from .views_api import gerty_api_router

gerty_static_files = [
    {
        "path": "/gerty/static",
        "name": "gerty_static",
    }
]

gerty_ext: APIRouter = APIRouter(prefix="/gerty", tags=["Gerty"])
gerty_ext.include_router(gerty_generic_router)
gerty_ext.include_router(gerty_api_router)

__all__ = ["db", "gerty_ext", "gerty_static_files"]
