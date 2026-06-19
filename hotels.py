import requests
import os 
from datetime import datetime, timedelta

# ================= API CONSTANTS =================

RAPID_API_HOST = "booking-com15.p.rapidapi.com"
BASE_URL = f"https://{RAPID_API_HOST}/api/v1/hotels"

_rapid_api_key = None

def get_rapid_api_key() -> str:
    global _rapid_api_key
    if _rapid_api_key is None:
        _rapid_api_key = os.environ.get("RAPID_API_KEY", "YOUR_RAPID_API_KEY_HERE")
    return _rapid_api_key


HEADERS = {
    "x-rapidapi-key": get_rapid_api_key(),
    "x-rapidapi-host": RAPID_API_HOST,
    "Content-Type": "application/json",
}


# ================= BUDGET CATEGORIES =================
#
#   LUXURY   → 5-star only  (propertyClass == 5)  → sorted by rating DESC
#   MID-RANGE→ 3-4 star     (propertyClass 3 or 4) → sorted by rating DESC
#   ECONOMY  → 1-2 star OR unrated (propertyClass 0-2) → sorted by price ASC
#
# Keywords accepted per category:
CATEGORY_KEYWORDS = {
    "luxury":    ["luxury", "luxurious", "5 star", "5star", "premium", "high end", "upscale"],
    "mid-range": ["mid", "midrange", "mid-range", "mid range", "3 star", "4 star",
                  "3star", "4star", "moderate", "standard", "average"],
    "economy":   ["economy", "budget", "cheap", "affordable", "low cost", "lowcost",
                  "inexpensive", "1 star", "2 star", "1star", "2star"],
}

def detect_category(user_input: str) -> str | None:
    """
    Maps what the user typed to one of: 'luxury', 'mid-range', 'economy'.
    Returns None if no match found.
    """
    text = user_input.strip().lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return category
    return None


# ================= API HELPERS =================

def _get(endpoint: str, params: dict) -> dict:
    url = f"{BASE_URL}/{endpoint}"
    response = requests.get(url, headers=HEADERS, params=params)
    if response.status_code == 200:
        return response.json()
    return {}


def get_destination(city: str) -> dict | None:
    data = _get("searchDestination", {"query": city})
    results = data.get("data", [])
    if results:
        first = results[0]
        return {
            "dest_id":     str(first["dest_id"]),
            "search_type": str(first["search_type"]),
        }
    return None


def fetch_hotels(city: str, adults: int = 1, room_qty: int = 1) -> list[dict]:
    """Fetches raw hotel list from the API (no filtering yet)."""
    destination = get_destination(city)
    if not destination:
        return []

    today      = datetime.now()
    arrival    = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    departure  = (today + timedelta(days=2)).strftime("%Y-%m-%d")

    params = {
        "dest_id":       destination["dest_id"],
        "search_type":   destination["search_type"],
        "arrival_date":  arrival,
        "departure_date":departure,
        "adults":        adults,
        "room_qty":      room_qty,
    }

    data       = _get("searchHotels", params)
    hotel_list = data.get("data", {}).get("hotels", [])

    hotels = []
    for item in hotel_list:
        prop = item.get("property", {})

        price_raw = (
            prop.get("priceBreakdown", {})
                .get("grossPrice", {})
                .get("value")
        )

        hotels.append({
            "hotelId":         str(prop.get("id") or ""),
            "name":            prop.get("name", "Unknown"),
            "location":        prop.get("wishlistName", ""),
            "rating":          float(prop.get("reviewScore") or 0),
            "reviewScoreWord": prop.get("reviewScoreWord", ""),
            "reviewCount":     int(prop.get("reviewCount") or 0),
            "propertyClass":   int(prop.get("propertyClass") or 0),   # star rating
            "price":           round(float(price_raw), 2) if price_raw else None,
            "currency":        prop.get("priceBreakdown", {})
                                   .get("grossPrice", {})
                                   .get("currency", "USD"),

        })

    return hotels


# ================= FILTERING =================

def filter_by_category(hotels: list[dict], category: str) -> list[dict]:
    """
    Keeps only hotels matching the star-class for the chosen category,
    then sorts them appropriately.
    """
    if category == "luxury":
        filtered = [h for h in hotels if h["propertyClass"] == 5]
        # Best-rated first
        return sorted(filtered, key=lambda h: h["rating"], reverse=True)

    elif category == "mid-range":
        filtered = [h for h in hotels if h["propertyClass"] in (3, 4)]
        return sorted(filtered, key=lambda h: h["rating"], reverse=True)

    elif category == "economy":
        filtered = [h for h in hotels if h["propertyClass"] in (0, 1, 2)]
        # Cheapest first (put None prices at the end)
        return sorted(filtered, key=lambda h: (h["price"] is None, h["price"] or 0))

    return hotels


# ================= DISPLAY =================

def display_hotels(hotels: list[dict], category: str):
    stars = {
        "luxury":    "★★★★★ (5-star)",
        "mid-range": "★★★☆☆ – ★★★★☆ (3-4 star)",
        "economy":   "★☆☆☆☆ – ★★☆☆☆ (budget / unrated)",
    }


    if not hotels:
        return

    for i, h in enumerate(hotels, 1):
        price_str = (
            f"{h['currency']} {h['price']:.2f}"
            if h["price"] is not None
            else "Price N/A"
        )
        stars_str = "★" * h["propertyClass"] if h["propertyClass"] else "unrated"
        score_str = (
            f"{h['rating']} {h['reviewScoreWord']} ({h['reviewCount']} reviews)"
            if h["rating"] > 0
            else "No reviews yet"
        )


# ================= MAIN FUNCTION =================

def search_hotels(city: str, flutter_user_level: str) -> dict:
    """
    Search and display hotels for a given city and budget preference.

    Parameters
    ----------
    city : str
        The city to search hotels in (e.g. "Cairo").
    flutter_user_level : str
        The user's budget preference (e.g. "luxury", "mid-range", "economy").

    Returns
    -------
    dict with keys:
        success  : bool
        category : str or None
        city     : str
        hotels   : list[dict]  — the filtered & sorted hotel list
    """
    if not city:
        return {"success": False, "category": None, "city": city, "hotels": []}

    category = detect_category(flutter_user_level)
    if not category:
        return {"success": False, "category": None, "city": city, "hotels": []}

    all_hotels = fetch_hotels(city)

    if not all_hotels:
        return {"success": False, "category": category, "city": city, "hotels": []}

    matched = filter_by_category(all_hotels, category)
    display_hotels(matched, category)

    return {
        "success":  True,
        "category": category,
        "city":     city,
        "hotels":   matched,
    }