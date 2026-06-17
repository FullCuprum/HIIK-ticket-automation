from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.db.database import AsyncSessionLocal
from app.routers import approvals, auth, employees, schedule, tickets, users
from app.services.user_seed import ensure_demo_users


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as session:
        await ensure_demo_users(session)
        await session.commit()
    yield


app = FastAPI(title="Diplom Ticket Automation", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tickets.router)
app.include_router(schedule.router)
app.include_router(approvals.router)
app.include_router(auth.router)
app.include_router(employees.router)
app.include_router(users.router)

app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/frontend/index.html")
