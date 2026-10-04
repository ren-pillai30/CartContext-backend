import os
import uuid
from dotenv import load_dotenv
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.sql import func

# Load the environment variables from the .env file
load_dotenv()

# Format the connection string for asyncpg
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Create the async engine
engine = create_async_engine(DATABASE_URL, echo=True)

# Create a configured "Session" class
AsyncSessionLocal = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

Base = declarative_base()

# Dependency generator to inject the database session into our FastAPI routes
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# --- SQLAlchemy Models ---

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Brand(Base):
    __tablename__ = "brands"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False)
    vader_sentiment_score = Column(Numeric(5, 4))
    news_cache = Column(JSONB)
    last_analyzed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Product(Base):
    __tablename__ = "products"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(UUID(as_uuid=True), ForeignKey("brands.id", ondelete="SET NULL"))
    name = Column(String(255), nullable=False)
    barcode = Column(String(100), unique=True)
    calories = Column(Integer)
    macros = Column(JSONB)
    data_source = Column(String(50), default="open_food_facts")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class GroceryNote(Base):
    __tablename__ = "grocery_notes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    raw_input = Column(Text, nullable=False)
    parsed_items = Column(JSONB)
    status = Column(String(50), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PantryInventory(Base):
    __tablename__ = "pantry_inventory"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"))
    receipt_string = Column(String(255))
    quantity = Column(Numeric(10, 2), default=1.0)
    is_impulse_buy = Column(Boolean, default=False)
    fuzzy_match_score = Column(Integer)
    added_at = Column(DateTime(timezone=True), server_default=func.now())