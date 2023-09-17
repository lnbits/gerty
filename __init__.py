from fastapi import APIRouter

from lnbits.db import Database
from lnbits.helpers import template_renderer

db = Database("ext_gerty")

gerty_static_files = [
    {
        "path": "/gerty/static",
        "name": "gerty_static",
    }
]


gerty_ext: APIRouter = APIRouter(prefix="/gerty", tags=["Gerty"])


def gerty_renderer():
    return template_renderer(["gerty/templates"])


from .views import *  # noqa: F401,F403
from .views_api import *  # noqa: F401,F403
