import math
from typing import List, Set, Dict, Tuple, Optional
from dataclasses import dataclass
import json

@dataclass
class ChildPlaceResponse:
    """Structured response for a child place"""
    name: str
    categories: str
    cost: Optional[float]
    day_time: str
    website: str
    address: Optional[str] = None

    def to_dict(self):
        return {
            "name": self.name,
            "categories": self.categories,
            "cost": self.cost,
            "day_time": self.day_time,
            "website": self.website,
            "address": self.address
        }


@dataclass
class PlaceResponse:
    """Structured response for a single place"""
    name: str
    categories: str
    cost: Optional[float]
    day_time: str
    website: str
    address: Optional[str] = None
    is_parent: bool = False
    children: List = None

    def __post_init__(self):
        if self.children is None:
            self.children = []

    def to_dict(self):
        result = {
            "name": self.name,
            "categories": self.categories,
            "cost": self.cost,
            "day_time": self.day_time,
            "website": self.website,
            "address": self.address,
            "is_parent": self.is_parent,
        }
        if self.is_parent:
            result["children"] = [child.to_dict() for child in self.children]
        return result


@dataclass
class DayResponse:
    """Structured response for a single day"""
    day_number: int
    places: List[PlaceResponse]

    def to_dict(self):
        return {
            "day": self.day_number,
            "places": [place.to_dict() for place in self.places]
        }


@dataclass
class ItineraryResponse:
    """Final structured response for the entire itinerary"""
    success: bool
    message: str
    itinerary: List[DayResponse]
    used_places: int
    total_places: int
    remaining_budget: float

    def to_dict(self):
        return {
            "success": self.success,
            "message": self.message,
            "itinerary": [day.to_dict() for day in self.itinerary],
            "used_places": self.used_places,
            "total_places": self.total_places,
            "remaining_budget": self.remaining_budget
        }

    def to_json(self):
        """Convert to JSON string for API response"""
        return json.dumps(self.to_dict())


def get_candidates(df, city, country=None):
    """Get all candidates from a specific city and optionally country"""
    filtered_df = df[df["city"] == city].copy()

    if country is not None:
        filtered_df = filtered_df[filtered_df["country"] == country].copy()

    return filtered_df


def compute_preference_score(row, user_prefs):
    """Compute normalized preference score based on user tags"""
    score = 0
    for tag in user_prefs:
        if tag in row and row[tag] == 1:
            score += 1

    if len(user_prefs) == 0:
        return 0

    return score / len(user_prefs)


def diversity_penalty(primary_tag, used_tags):
    """Apply penalty if tag already used today"""
    if primary_tag is None:
        return 1.0
    if primary_tag in used_tags:
        return 0.7
    return 1.0


def calculate_distance(place1_coords, place2_coords):
    """
    Calculate distance between two places using Haversine formula
    coords format: (latitude, longitude)
    Returns distance in km
    """
    if place1_coords is None or place2_coords is None:
        return float('inf')

    lat1, lon1 = place1_coords
    lat2, lon2 = place2_coords

    R = 6371  # Earth radius in km

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)

    c = 2 * math.asin(math.sqrt(a))
    distance = R * c

    return distance


def distance_weight(distance, max_distance=15.0, min_weight=0.3):
    """Convert distance to weight (closer = higher weight)"""
    if distance >= max_distance:
        return min_weight

    return 1.0 - (distance / max_distance) * (1.0 - min_weight)


def get_time_weight(day_time, position_in_day):
    """Assign time-based weight based on position in daily itinerary"""
    time_weights = {
        0: {"morning": 1.0, "afternoon": 0.6, "night": 0.2},
        1: {"morning": 0.7, "afternoon": 1.0, "night": 0.5},
        2: {"morning": 0.3, "afternoon": 0.7, "night": 1.0}
    }

    if position_in_day not in time_weights:
        return 0.5

    day_time = day_time.lower() if day_time else "afternoon"
    return time_weights[position_in_day].get(day_time, 0.5)


def score_place(row, user_prefs, used_tags, position_in_day, last_place_coords=None):
    """Score a place considering multiple factors"""
    try:
        pref_score = compute_preference_score(row, user_prefs)
        popularity = row.get("llama-3.3-70b-versatile_match_score", 50) / 100
        primary_tag = get_primary_tag(row, user_prefs)
        diversity = diversity_penalty(primary_tag, used_tags)

        day_time = row.get("day_time", "afternoon")
        time_weight = get_time_weight(day_time, position_in_day)

        distance_w = 1.0
        if last_place_coords is not None:
            try:
                current_coords = (row.get("latitude"), row.get("longitude"))
                distance = calculate_distance(last_place_coords, current_coords)
                distance_w = distance_weight(distance)
            except (TypeError, ValueError):
                distance_w = 1.0

        final_score = (
            0.45 * pref_score +
            0.15 * popularity +
            0.20 * time_weight +
            0.10 * distance_w +
            0.10 * diversity
        )

        return final_score

    except Exception:
        return 0.0


def rank_places(df, user_prefs, position_in_day, used_tags=None, last_place_coords=None):
    """Rank places based on score"""
    if used_tags is None:
        used_tags = set()

    try:
        if df.empty:
            return df.copy()

        df = df.copy()
        scores = []

        for idx, row in df.iterrows():
            score = score_place(row, user_prefs, used_tags, position_in_day, last_place_coords)
            scores.append(score)

        df["score"] = scores
        return df.sort_values("score", ascending=False)

    except Exception:
        return df.copy()


def get_primary_tag(row, user_prefs):
    """Get the first matching preference tag for a place"""
    for tag in user_prefs:
        if tag in row and row[tag] == 1:
            return tag
    return None


def get_price_column(price_type="foreign"):
    """Get the appropriate price column name"""
    price_columns = {
        "foreign": "foreigner price",
        "egyptian": "egyptian price"
    }
    return price_columns.get(price_type, "foreigner price")


def extract_place_data(row, price_column, child_df=None):
    """Extract required fields for place response, attaching children if place is a parent"""
    is_parent = str(row.get("place_type", "")).strip().lower() == "parent"
    children = []

    if is_parent and child_df is not None and not child_df.empty:
        place_name = str(row.get("name", ""))
        child_rows = child_df[child_df["parent"] == place_name]
        for _, child_row in child_rows.iterrows():
            child_cost = child_row.get(price_column)
            children.append(ChildPlaceResponse(
                name=str(child_row.get("name", "Unknown Place")),
                categories=str(child_row.get("categories", "")),
                cost=float(child_cost) if child_cost is not None and str(child_cost) != "nan" else None,
                day_time=str(child_row.get("day_time", "afternoon")),
                website=str(child_row.get("website", "")),
                address=str(child_row.get("address", "")) or None
            ))

    cost_val = row.get(price_column)
    return PlaceResponse(
        name=str(row.get("name", "Unknown Place")),
        categories=str(row.get("categories", "")),
        cost=float(cost_val) if cost_val is not None and str(cost_val) != "nan" else None,
        day_time=str(row.get("day_time", "afternoon")),
        website=str(row.get("website", "")),
        address=str(row.get("address", "")) or None,
        is_parent=is_parent,
        children=children
    )


def build_day(candidates, budget, user_prefs, used_places, price_type="foreign", child_df=None):
    """Build a single day's itinerary"""
    day_places = []
    used_tags = set()
    remaining_budget = budget
    last_place_coords = None

    current_candidates = candidates.copy()
    max_places_per_day = 3
    price_column = get_price_column(price_type)

    for position in range(max_places_per_day):
        ranked = rank_places(
            current_candidates,
            user_prefs,
            position_in_day=position,
            used_tags=used_tags,
            last_place_coords=last_place_coords
        )

        found = False
        for _, row in ranked.iterrows():
            if row["name"] in used_places:
                continue

            cost = row.get(price_column)
            if cost is not None and cost > remaining_budget:
                continue

            place_response = extract_place_data(row, price_column, child_df=child_df)
            day_places.append(place_response)

            primary_tag = get_primary_tag(row, user_prefs)
            used_tags.add(primary_tag)
            used_places.add(row["name"])

            if cost:
                remaining_budget -= cost

            try:
                last_place_coords = (row.get("latitude"), row.get("longitude"))
            except:
                last_place_coords = None

            current_candidates = current_candidates[current_candidates["name"] != row["name"]]
            found = True
            break

        if not found:
            break

    return day_places, remaining_budget


def build_itinerary_api(df, city: str, days: int, budget: float,
                        user_prefs: List[str], country: Optional[str] = None,
                        price_type: str = "foreign",
                        child_df=None) -> ItineraryResponse:
    """
    Build a multi-day itinerary with REST API response format

    Parameters:
    -----------
    df : DataFrame
        The places dataframe
    city : str
        City name to filter by
    days : int
        Number of days for the itinerary
    budget : float
        Total budget for the trip
    user_prefs : List[str]
        User preference tags
    country : str, optional
        Country name to filter by
    price_type : str
        Price type: "foreign" (default) or "egyptian"
    child_df : DataFrame, optional
        DataFrame of child places to attach under parent places

    Returns:
    --------
    ItineraryResponse : Structured response object
    """

    try:
        if not isinstance(user_prefs, (set, list)):
            return ItineraryResponse(
                success=False,
                message="❌ User preferences must be a list.",
                itinerary=[],
                used_places=0,
                total_places=0,
                remaining_budget=budget
            )

        user_prefs = set(user_prefs)

        if len(user_prefs) == 0:
            return ItineraryResponse(
                success=False,
                message="❌ Please select at least one preference category.",
                itinerary=[],
                used_places=0,
                total_places=0,
                remaining_budget=budget
            )

        candidates = get_candidates(df, city, country)

        if candidates.empty:
            country_text = f" in {country}" if country else ""
            return ItineraryResponse(
                success=False,
                message=f"😞 We don't have any places in {city}{country_text} yet. Check back soon!",
                itinerary=[],
                used_places=0,
                total_places=0,
                remaining_budget=budget
            )

        price_column = get_price_column(price_type)
        if price_column not in candidates.columns:
            price_type = "foreign"
            price_column = "foreigner price"

        itinerary_days = []
        used_places = set()
        current_budget = budget

        for day_num in range(days):
            daily_pool = candidates[~candidates["name"].isin(used_places)]

            if daily_pool.empty:
                break

            day_places, current_budget = build_day(
                daily_pool,
                current_budget,
                user_prefs,
                used_places,
                price_type=price_type,
                child_df=child_df
            )

            if not day_places:
                break

            itinerary_days.append(DayResponse(day_number=day_num + 1, places=day_places))

        if len(used_places) == len(candidates):
            message = f"🎉 Amazing! You've covered all {len(used_places)} incredible places we have in {city}{' in ' + country if country else ''}! Your journey is complete. Come back again for more adventures! ✨"
        elif len(used_places) > 0:
            message = f"✅ Itinerary created! You've explored {len(used_places)} wonderful places out of {len(candidates)} available."
        else:
            message = "❌ Could not create itinerary with the given constraints."

        return ItineraryResponse(
            success=len(itinerary_days) > 0,
            message=message,
            itinerary=itinerary_days,
            used_places=len(used_places),
            total_places=len(candidates),
            remaining_budget=current_budget
        )

    except Exception as e:
        return ItineraryResponse(
            success=False,
            message="😔 Oops! We encountered an unexpected issue while planning your adventure. Please try again in a moment.",
            itinerary=[],
            used_places=0,
            total_places=0,
            remaining_budget=budget
        )


def itinerary_endpoint(request_data: dict) -> dict:
    try:
        response = build_itinerary_api(
            df=request_data.get("df"),
            city=request_data.get("city"),
            days=request_data.get("days"),
            budget=request_data.get("budget"),
            user_prefs=request_data.get("preferences", []),
            country=request_data.get("country"),
            price_type=request_data.get("price_type", "foreign")
        )

        return response.to_dict()

    except Exception as e:
        return {
            "success": False,
            "message": "😔 Oops! We encountered an unexpected issue while planning your adventure. Please try again in a moment.",
            "itinerary": [],
            "used_places": 0,
            "total_places": 0,
            "remaining_budget": request_data.get("budget", 0)
        }