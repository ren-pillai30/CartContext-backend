import os
import json
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from google import genai
from google.genai import types
from thefuzz import process

from app.models import get_db, User, GroceryNote, PantryInventory, Product, Brand
from app.tasks import enrich_product_data

# Initialize the router
router = APIRouter(tags=["Smart Planning & Analytics"])

# Configure Gemini Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_ID = "gemini-3.8-flash"

# --- Pydantic Schemas ---
class NoteRequest(BaseModel):
    email: str
    raw_input: str

# --- 1. Smart Planning Route ---
@router.post("/notes/parse")
async def parse_grocery_note(request: NoteRequest, db: AsyncSession = Depends(get_db)):
    user_result = await db.execute(select(User).where(User.email == request.email))
    user = user_result.scalars().first()
    
    if not user:
        user = User(email=request.email)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    prompt = f"""
    You are an intelligent grocery lifecycle manager. Extract the grocery items and their quantities from the following messy text.
    Return a valid JSON array of objects, where each object has strictly two keys: 'item' (string) and 'quantity' (number or string).
    
    Text: "{request.raw_input}"
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        parsed_items = json.loads(response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini Parsing Failed: {str(e)}")

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

# --- 2. Frictionless Checkout & Fuzzy Reconciliation Route ---
@router.post("/checkout/ocr")
async def process_receipt_ocr(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    user_result = await db.execute(select(User).where(User.email == email))
    user = user_result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Create a grocery note first.")

    image_bytes = await file.read()
    image_part = types.Part.from_bytes(
        data=image_bytes,
        mime_type=file.content_type or "image/jpeg"
    )

    vision_prompt = """
    Analyze this grocery receipt image. Extract all purchased line items, quantities, and prices.
    Return a valid JSON array of objects, where each object has keys: 'item_string' (the exact cryptic text on the receipt) and 'quantity' (number).
    """

    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=[vision_prompt, image_part],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        receipt_items = json.loads(response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini Vision OCR Failed: {str(e)}")

    notes_result = await db.execute(
        select(GroceryNote).where(GroceryNote.user_id == user.id, GroceryNote.status == "active")
    )
    active_notes = notes_result.scalars().all()

    planned_item_names = []
    for note in active_notes:
        if note.parsed_items:
            for p in note.parsed_items:
                if "item" in p:
                    planned_item_names.append(p["item"])

    reconciled_results = []
    for r_item in receipt_items:
        receipt_str = r_item.get("item_string", "")
        qty = r_item.get("quantity", 1.0)
        
        match_score = 0
        is_impulse = True

        if planned_item_names:
            best_match, match_score = process.extractOne(receipt_str, planned_item_names)
            if match_score >= 60:
                is_impulse = False

        background_tasks.add_task(enrich_product_data, receipt_str, db)

        pantry_entry = PantryInventory(
            user_id=user.id,
            receipt_string=receipt_str,
            quantity=qty,
            is_impulse_buy=is_impulse,
            fuzzy_match_score=match_score
        )
        db.add(pantry_entry)
        reconciled_results.append({
            "receipt_string": receipt_str,
            "quantity": qty,
            "fuzzy_match_score": match_score,
            "is_impulse_buy": is_impulse
        })

    await db.commit()

    return {
        "message": "Receipt processed and reconciled successfully",
        "reconciled_items": reconciled_results
    }

# --- 3. Get User Pantry Inventory ---
@router.get("/pantry/{email}")
async def get_pantry_inventory(email: str, db: AsyncSession = Depends(get_db)):
    user_result = await db.execute(select(User).where(User.email == email))
    user = user_result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = await db.execute(
        select(PantryInventory).where(PantryInventory.user_id == user.id)
    )
    items = result.scalars().all()

    return {
        "user_email": email,
        "total_items": len(items),
        "inventory": [
            {
                "id": str(item.id),
                "receipt_string": item.receipt_string,
                "quantity": float(item.quantity) if item.quantity else 1.0,
                "is_impulse_buy": item.is_impulse_buy,
                "fuzzy_match_score": item.fuzzy_match_score,
                "added_at": item.added_at.isoformat() if item.added_at else None
            }
            for item in items
        ]
    }

# --- 4. Get User Shopping Analytics ---
@router.get("/analytics/{email}")
async def get_shopping_analytics(email: str, db: AsyncSession = Depends(get_db)):
    user_result = await db.execute(select(User).where(User.email == email))
    user = user_result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = await db.execute(
        select(PantryInventory).where(PantryInventory.user_id == user.id)
    )
    items = result.scalars().all()

    if not items:
        return {"user_email": email, "impulse_buy_rate": 0.0, "total_items_scanned": 0}

    total_count = len(items)
    impulse_count = sum(1 for i in items if i.is_impulse_buy)
    impulse_rate = round((impulse_count / total_count) * 100, 2)

    return {
        "user_email": email,
        "total_items_scanned": total_count,
        "impulse_items_count": impulse_count,
        "planned_items_count": total_count - impulse_count,
        "impulse_buy_rate_percent": impulse_rate
    }