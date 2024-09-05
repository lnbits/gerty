from http import HTTPStatus

from fastapi import APIRouter, Depends, Request
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer
from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse

from .crud import get_gerty

gerty_generic_router = APIRouter()


def gerty_renderer():
    return template_renderer(["gerty/templates"])


@gerty_generic_router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return gerty_renderer().TemplateResponse(
        "gerty/index.html", {"request": request, "user": user.dict()}
    )


@gerty_generic_router.get("/{gerty_id}", response_class=HTMLResponse)
async def display(request: Request, gerty_id):
    gerty = await get_gerty(gerty_id)
    if not gerty:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Gerty does not exist."
        )
    return gerty_renderer().TemplateResponse(
        "gerty/gerty.html", {"request": request, "gerty": gerty_id}
    )
