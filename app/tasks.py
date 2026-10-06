import httpx
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models import Product, Brand

analyzer = SentimentIntensityAnalyzer()

async def enrich_product_data(item_name: str, db: AsyncSession):
    """
    Queries Open Food Facts for nutrition data and evaluates brand sentiment using VADER.
    """
    async with httpx.AsyncClient() as client:
        # Search Open Food Facts by the raw item name
        url = f"https://world.openfoodfacts.org/cgi/search.pl?search_terms={item_name}&search_simple=1&action=process&json=1"
        try:
            # The API asks clients to send a descriptive User-Agent
            response = await client.get(url, headers={"User-Agent": "CartContextApp/1.0"})
            data = response.json()
        except Exception:
            return

        if not data.get("products"):
            return
            
        # Extract the top hit
        top_hit = data["products"][0]
        brand_name = top_hit.get("brands", "Generic").split(",")[0].strip()
        barcode = top_hit.get("code", "")
        nutriments = top_hit.get("nutriments", {})
        calories = nutriments.get("energy-kcal_100g", 0)

    # Compute VADER sentiment score for the brand
    sentiment_dict = analyzer.polarity_scores(brand_name)
    compound_score = sentiment_dict["compound"]

    # Save or update the Brand in Neon
    brand_result = await db.execute(select(Brand).where(Brand.name == brand_name))
    brand = brand_result.scalars().first()
    
    if not brand:
        brand = Brand(
            name=brand_name,
            vader_sentiment_score=compound_score
        )
        db.add(brand)
        await db.flush() # Flush to generate the brand.id

    # Save or update the Product in Neon
    product_result = await db.execute(select(Product).where(Product.barcode == barcode))
    product = product_result.scalars().first()
    
    if not product:
        product = Product(
            brand_id=brand.id,
            name=top_hit.get("product_name", item_name),
            barcode=barcode,
            calories=calories,
            macros=nutriments,
            data_source="open_food_facts"
        )
        db.add(product)
        await db.commit()