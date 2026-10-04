from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.models import get_db
from app.routes import router as api_router

app = FastAPI(title="CartContext AI")

# Mount the routes
app.include_router(api_router)

@app.get("/")
async def root():
    return {"status": "healthy", "service": "CartContext AI Core"}

@app.get("/health/db")
async def check_db(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    value = result.scalar()
    return {"database_connected": value == 1}