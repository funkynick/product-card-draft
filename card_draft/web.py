from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from .llm import ApiClient, LlmError
from .parsing import InputError, parse_product
from .render import render_markdown
from .service import generate_card

app = FastAPI(title="Черновик карточки товара")

INDEX_PAGE = Path(__file__).with_name("index.html")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_PAGE)


@app.post("/api/card")
async def create_card(request: Request) -> JSONResponse:
    try:
        product = parse_product(await request.body())
    except InputError as exc:
        return JSONResponse({"errors": exc.errors}, status_code=422)

    try:
        card = await run_in_threadpool(generate_card, product, ApiClient())
    except LlmError as exc:
        return JSONResponse({"errors": [str(exc)]}, status_code=502)

    return JSONResponse({"card": card.model_dump(), "markdown": render_markdown(card)})
