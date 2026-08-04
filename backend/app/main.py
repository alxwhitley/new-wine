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

# Stage 2 cutover -- async answer path routes, gated on ASYNC_ANSWER_ENABLED
# (default "false"). When OFF (the default) these routes are NOT mounted, so the
# app's route table is byte-identical to before this change and the live /chat
# path is entirely unaffected. Enabling the env (a deploy) makes the routes exist;
# the actual seconds-reversible TRAFFIC switch is async_answer_config.serving_enabled,
# which the frontend consults via GET /async-chat/mode. Both default OFF.
if os.environ.get("ASYNC_ANSWER_ENABLED", "false").lower() == "true":
    from app.routers import async_chat
    app.include_router(async_chat.router, prefix="/async-chat", tags=["async-chat"])
    logging.getLogger(__name__).info("Async answer routes MOUNTED (ASYNC_ANSWER_ENABLED=true)")

@app.get("/")
async def root():
    return {"message": "Rhemata API"}