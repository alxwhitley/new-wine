import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Rhemata", description="Theological knowledge base and AI chat tool")

allowed_origins = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .routers import chat, search, document, ingest

app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(document.router, prefix="/document", tags=["document"])
app.include_router(ingest.router, prefix="/ingest", tags=["ingest"])

@app.get("/")
async def root():
    return {"message": "Rhemata API"}