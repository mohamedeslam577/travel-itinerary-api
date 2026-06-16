from fastapi import FastAPI , HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import pandas as pd
import os
from itinerary import build_itinerary
from hotels import search_hotels
from groq_client import get_groq_client
from sqlalchemy import create_engine

app = FastAPI(title="Travel Planner API",description="Create personalized travel itineraries", version="1.0.0")

# =========================
# CORS FIX FOR FLUTTER WEB
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (good for testing)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Load dataframes once at startup ────────────────────────────────────────
# Replace these paths with your actual CSV/parquet files
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL is None:
    DATABASE_URL = "postgresql://postgres:YqavFXcTXlyBuMNKTWObIkZeiGodEuiA@kodama.proxy.rlwy.net:26773/railway"

DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

engine = create_engine(DATABASE_URL)

recommendation_df = pd.read_sql(
    "SELECT * FROM recommendation_places",
    engine
)

child_rows = pd.read_sql(
    "SELECT * FROM child_places",
    engine
)



# ─── Request schema ──────────────────────────────────────────────────────────

class TripRequest(BaseModel):
    flutter_country: str
    flutter_city: str
    flutter_days: int
    flutter_budget: float
    flutter_user_prefs: List[str]
    flutter_price_type: Optional[str] = "foreign"   # optional, default foreign
    flutter_user_level: Optional[str] = None         # optional
    flutter_has_children: Optional[str] = "False"
    flutter_trip_style: Optional[str] = ""
    flutter_fav_weather: Optional[str] = ""
    flutter_fav_atmosphere: Optional[str] = ""
    flutter_fav_mood: Optional[str] = ""


# ─── Response helpers ────────────────────────────────────────────────────────

def _egypt_trip_response(req: TripRequest) -> dict:
    """Build Egypt itinerary with our recommendation engine, then format via Groq."""
    itinerary_result = build_itinerary(
        df=recommendation_df,
        city=req.flutter_city,
        country=req.flutter_country,
        days=req.flutter_days,
        budget=req.flutter_budget,
        user_prefs=req.flutter_user_prefs,
        price_type=req.flutter_price_type or "foreign",
        child_rows=child_rows,
    )

    egypt_prompt = f"""
You are a professional travel itinerary presenter.

Transform the provided itinerary JSON into a visually appealing, premium travel guide.

Rules:
* Preserve all itinerary data exactly as provided.
* Do not remove, reorder, merge, summarize, or modify activities.
* Do not change place names, descriptions, timings, costs, categories, or recommendations.
* Do not invent new activities, attractions, restaurants, hotels, schedules, or prices.
* You may improve formatting, readability, section titles, emojis, and presentation only.
* Every activity and cost in the JSON must appear in the output.

Use the traveler's preferences ONLY to personalize:
* The title
* The introduction
* Day theme names
* Traveler tips
* Practical recommendations

Never modify the itinerary itself based on preferences.

Output format:

# ✈️ Trip Title

Short engaging introduction.

## 📊 Trip Summary

Display all available trip-level information.

For each day:

# 🗓️ Day X — Theme

## 🌅 Morning
* Activity name
* Full description
* 💰 Cost

## ☀️ Afternoon
* Activity name
* Full description
* 💰 Cost

## 🌙 Evening
* Activity name
* Full description
* 💰 Cost

### 💵 Daily Cost

After all days:

## 💡 Traveler Tips
Provide 3-5 useful tips tailored to the user's preferences and travel style.

## 💰 Budget Breakdown
Display daily costs and total budget exactly as provided.

Use clean Markdown, emojis, and a warm professional tone.

Traveler Preferences:
* Interests: {req.flutter_user_prefs}
* Has Children: {req.flutter_has_children}
* Trip Style: {req.flutter_trip_style}
* Preferred Weather: {req.flutter_fav_weather}
* Preferred Atmosphere: {req.flutter_fav_atmosphere}
* Preferred Mood: {req.flutter_fav_mood}

Itinerary JSON:
{itinerary_result}
"""

    client = get_groq_client()
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": egypt_prompt}],
            temperature=0.7,
            max_tokens=3000,
        )
        trip_text = response.choices[0].message.content
    except Exception as groq_err:
        # Groq failed → return raw itinerary result as string
        trip_text = str(itinerary_result)

    return {"trip_plan": trip_text, "raw": itinerary_result}


def _any_country_trip_response(req: TripRequest) -> dict:
    """Generate itinerary for non-Egypt destinations entirely via Groq."""
    any_country_prompt = f"""
You are an expert travel planner and professional travel guide.

Your task is to create a complete personalized travel itinerary based on the user's preferences and trip details.

Requirements:
* Generate a realistic itinerary for the specified destination.
* Select attractions, experiences, shopping areas, cultural sites, nature spots, entertainment venues, and restaurants that match the user's interests.
* Prioritize recommendations that align with the user's preferences, trip style, atmosphere, mood, and weather preferences.
* If the user has children, include family-friendly options whenever appropriate.
* Respect the user's budget across the entire trip.
* Distribute activities naturally across the trip duration.
* Avoid repeating places or very similar experiences.
* Use real and well-known places whenever possible.
* Make recommendations specific to the destination.

ITINERARY GENERATION RULES:
* Generate exactly 3 activities per day:
  * One Morning activity
  * One Afternoon activity
  * One Evening activity
* Each activity must correspond to a single destination or place.

Output Format:

# ✈️ [Creative Trip Title]

Write a short exciting introduction tailored to the traveler.

## 📊 Trip Summary
* Destination
* Duration
* Budget
* Trip Style
* Main Interests

For each day:

# 🗓️ Day X — [Theme Name]

## 🌅 Morning
📍 Place Name
* Description
* Why it matches the traveler's interests
* 💰 Estimated Cost

## ☀️ Afternoon
📍 Place Name
* Description
* Why it matches the traveler's interests
* 💰 Estimated Cost

## 🌙 Evening
📍 Place Name
* Description
* Why it matches the traveler's interests
* 💰 Estimated Cost

### 💵 Daily Cost

After all days:

## 💡 Traveler Tips
Provide 3-5 practical tips tailored to the traveler's profile and destination.

## 💰 Budget Breakdown
* Cost per day
* Total Estimated Cost

Trip Details:
* Country: {req.flutter_country}
* City: {req.flutter_city}
* Days: {req.flutter_days}
* Budget: {req.flutter_budget}

Traveler Preferences:
* Interests: {req.flutter_user_prefs}
* Has Children: {req.flutter_has_children}
* Trip Style: {req.flutter_trip_style}
* Preferred Weather: {req.flutter_fav_weather}
* Preferred Atmosphere: {req.flutter_fav_atmosphere}
* Preferred Mood: {req.flutter_fav_mood}
"""

    client = get_groq_client()
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": any_country_prompt}],
            temperature=0.7,
            max_tokens=2000,
        )
        trip_text = response.choices[0].message.content
    except Exception:
        trip_text = "Sorry, there was an error generating your itinerary. Please try again."

    return {"trip_plan": trip_text}


def _hotels_response(req: TripRequest) -> dict:
    """Search hotels and format via Groq. Only called when user_level is provided."""
    hotels_result = search_hotels(req.flutter_city, req.flutter_user_level)

    hotels_prompt = f"""You are a travel assistant.
The user selected a hotel preference level.
Write a short and friendly introduction (1-2 sentences max) telling the user that these hotels match their selected accommodation level.
Then present the provided hotel results in a clean, easy-to-read format, display property class as stars.
like this: name , price , and stars as ⭐
At the end, add a short note like:
"Want to explore more? You can view additional details, amenities, and photos by searching for the hotel name in the Hotels section of the app."
Keep the response concise, professional, and user-friendly.
Do not invent any information.
Use only the hotel data provided below.
Hotels:
{hotels_result}
"""

    client = get_groq_client()
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": hotels_prompt}],
            temperature=0.7,
            max_tokens=2000,
        )
        hotels_text = response.choices[0].message.content
    except Exception:
        # Groq failed → return raw hotel results
        hotels_text = str(hotels_result)

    return {"hotels": hotels_text, "raw": hotels_result}


# ─── Main endpoint ───────────────────────────────────────────────────────────

@app.post("/plan")
def plan_trip(req: TripRequest):
    result = {}

    # ── Trip plan ──────────────────────────────────────────────────────────
    if req.flutter_country.strip().lower() == "egypt":
        result.update(_egypt_trip_response(req))
    else:
        result.update(_any_country_trip_response(req))

    # ── Hotels (only if user_level provided) ──────────────────────────────
    if req.flutter_user_level:
        result.update(_hotels_response(req))

    return result


@app.get("/health")
def health():
    return {"status": "ok"}
