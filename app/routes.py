import os
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import google.generativeai as genai

from app.models import get_db, User, GroceryNote

# Initialize the router
router = APIRouter(tags=["Smart Planning"])

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Update to the current 3.8 production model endpoint
model = genai.GenerativeModel("gemini-3.8-flash")

# --- Pydantic Schemas for Request Validation ---
class NoteRequest(BaseModel):
    email: str
    raw_input: str

# --- API Endpoints ---
@router.post("/notes/parse")
async def parse_grocery_note(request: NoteRequest, db: AsyncSession = Depends(get_db)):
    # 1. Get or Create User (Handles our Foreign Key requirement)
    user_result = await db.execute(select(User).where(User.email == request.email))
    user = user_result.scalars().first()
    
    if not user:
        user = User(email=request.email)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # 2. LLM Orchestration
    prompt = f"""
    You are an intelligent grocery lifecycle manager. Extract the grocery items and their quantities from the following messy text.
    Return a valid JSON array of objects, where each object has strictly two keys: 'item' (string) and 'quantity' (number or string).
    
    Text: "{request.raw_input}"
    """
    
    try:
        # Enforce strict JSON generation
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(response_mime_type="application/json")
        )
        parsed_items = json.loads(response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini Parsing Failed: {str(e)}")

    # 3. Save to Neon Database
    new_note = GroceryNote(
        user_id=user.id,
        raw_input=request.raw_input,
        parsed_items=parsed_items,
        status="active"
    )
    db.add(new_note)
    await db.commit()
    await db.refresh(new_note)

    return {
        "message": "Note successfully parsed and saved",
        "note_id": new_note.id,
        "parsed_items": new_note.parsed_items
    }