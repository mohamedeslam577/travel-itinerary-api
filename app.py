from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd
from itinerary_rest_api import build_itinerary_api
from sqlalchemy import create_engine
import os

app = FastAPI(
    title="Itinerary API",
    description="Create personalized travel itineraries",
    version="1.0.0"
)

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

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL is None:
    DATABASE_URL = "postgresql://postgres:YqavFXcTXlyBuMNKTWObIkZeiGodEuiA@kodama.proxy.rlwy.net:26773/railway"

DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

engine = create_engine(DATABASE_URL)

recommendation_df = pd.read_sql(
    "SELECT * FROM recommendation_places",
    engine
)

child_df = pd.read_sql(
    "SELECT * FROM child_places",
    engine
)


# =========================
# REQUEST MODEL
# =========================
class ItineraryRequest(BaseModel):
    city: str
    country: Optional[str] = None
    days: int
    budget: float
    preferences: List[str]
    price_type: Optional[str] = "foreign"

    class Config:
        json_schema_extra = {
            "example": {
                "city": "Cairo",
                "country": "Egypt",
                "days": 3,
                "budget": 100000000,
                "preferences": [
                    "Nightlife & Festive",
                    "Shopping",
                    "Nature & Adventure"
                ],
                "price_type": "foreign"
            }
        }


# =========================
# RESPONSE MODELS
# =========================
class ChildPlaceModel(BaseModel):
    name: str
    categories: str
    cost: Optional[float]
    day_time: str
    website: str
    address: Optional[str] = None


class PlaceModel(BaseModel):
    name: str
    categories: str
    cost: Optional[float]
    day_time: str
    website: str
    address: Optional[str] = None
    is_parent: bool = False
    children: Optional[List[ChildPlaceModel]] = []


class DayModel(BaseModel):
    day: int
    places: List[PlaceModel]


class ItineraryResponseModel(BaseModel):
    success: bool
    message: str
    itinerary: List[DayModel]
    used_places: int
    total_places: int
    remaining_budget: float


# =========================
# CREATE ITINERARY
# =========================
@app.post("/api/itinerary", response_model=ItineraryResponseModel)
async def create_itinerary(request: ItineraryRequest):
    try:
        response = build_itinerary_api(
            df=recommendation_df,
            city=request.city,
            country=request.country,
            days=request.days,
            budget=request.budget,
            user_prefs=request.preferences,
            price_type=request.price_type,
            child_df=child_df
        )

        return response.to_dict()

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="😔 Oops! We encountered an unexpected issue while planning your adventure. Please try again in a moment."
        )


# =========================
# HEALTH CHECK
# =========================
@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "message": "Itinerary API is running"
    }


# =========================
# ROOT
# =========================
@app.get("/")
async def root():
    return {
        "name": "Itinerary API",
        "version": "1.0.0",
        "description": "Create personalized travel itineraries",
        "endpoints": {
            "create_itinerary": "/api/itinerary (POST)",
            "health_check": "/api/health (GET)",
            "docs": "/docs"
        }
    }