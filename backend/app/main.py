import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Rhemata", description="Theological knowledge base and AI chat tool")

allowed_origins = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import chat, search, document, ingest, ingest_queue, study, admin, feedback, library, pastors_notes, usage, account

app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(document.router, prefix="/document", tags=["document"])
app.include_router(ingest.router, prefix="/ingest", tags=["ingest"])
app.include_router(ingest_queue.router, prefix="/ingest-queue", tags=["ingest-queue"])
app.include_router(study.router, prefix="/study", tags=["study"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
app.include_router(library.router, prefix="/library", tags=["library"])
app.include_router(pastors_notes.router, prefix="/pastors-notes", tags=["pastors-notes"])
app.include_router(usage.router, prefix="/usage", tags=["usage"])
app.include_router(account.router, prefix="/account", tags=["account"])

@app.get("/")
async def root():
    return {"message": "Rhemata API"}