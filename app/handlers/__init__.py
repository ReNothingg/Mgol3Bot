from __future__ import annotations

from aiogram import Dispatcher

from app.handlers import admin, events, my, start, submissions


def setup_routers(dp: Dispatcher) -> None:
    dp.include_router(start.router)
    dp.include_router(events.router)
    dp.include_router(my.router)
    dp.include_router(submissions.router)
    dp.include_router(admin.router)

