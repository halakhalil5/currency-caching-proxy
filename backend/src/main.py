from fastapi import FastAPI

from routes.rates_routes import router as rates_router
from routes.health_routes import router as health_router

app = FastAPI()

app.include_router(rates_router)
app.include_router(health_router)
