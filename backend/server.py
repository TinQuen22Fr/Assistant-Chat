import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

from fastapi import FastAPI  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from auth import router as auth_router, seed_test_user  # noqa: E402
from chat import router as chat_router  # noqa: E402
from memory import router as memory_router  # noqa: E402
from imports import cleanup_sessions, router as imports_router  # noqa: E402
import io  # noqa: E402
import zipfile  # noqa: E402
from fastapi.responses import FileResponse, Response  # noqa: E402
from db import client, create_indexes  # noqa: E402
from llm_provider import active_provider  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

app = FastAPI(
    title="Gemini Perso API",
    version="1.0.0",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url=None,
)


@app.get("/api/")
async def root():
    return {"message": "Gemini Perso API", "provider": active_provider()}


app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(memory_router)
app.include_router(imports_router)

REPO_DIR = Path(__file__).resolve().parent.parent
BUNDLE_FILES = ["DEPLOIEMENT.md", "backend/requirements.txt", "backend/.env.example",
                "frontend/.env.example", "deploy/nginx.conf", "deploy/gemini-perso.service",
                "deploy/docker-compose.yml", "deploy/Dockerfile.backend", "deploy/backup.sh"]


@app.get("/api/deploy/guide")
async def deploy_guide():
    return FileResponse(REPO_DIR / "DEPLOIEMENT.md", media_type="text/markdown; charset=utf-8",
                        filename="DEPLOIEMENT.md")


@app.get("/api/deploy/bundle")
async def deploy_bundle():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in BUNDLE_FILES:
            if (REPO_DIR / rel).exists():
                zf.write(REPO_DIR / rel, f"gemini-perso-deploy/{rel}")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="gemini-perso-deploy.zip"'})

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ["CORS_ORIGINS"].split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await create_indexes()
    await seed_test_user()
    cleanup_sessions()
    if active_provider() != "google-account":
        logging.getLogger("gemini-perso").warning("Session compte Google non active : le chat ne fonctionnera pas.")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
