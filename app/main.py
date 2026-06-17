from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.routers import approvals, auth, employees, schedule, tickets

app = FastAPI(title="Diplom Ticket Automation")

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

app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/frontend/index.html")
