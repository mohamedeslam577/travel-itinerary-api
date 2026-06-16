import math
from typing import List, Set, Dict, Tuple, Optional


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

    return score / len(user_prefs)  # normalize 0 to 1


def is_affordable(current_budget, place_cost):
    """Check if a place is within budget"""
    if place_cost is None:
        return True  # unknown treat as free-safe
    return place_cost <= current_budget


def diversity_penalty(primary_tag, used_tags):
    """Apply penalty if tag already used today"""
    if primary_tag is None:
        return 1.0
    if primary_tag in used_tags:
        return 0.7  # penalty
    return 1.0


def calculate_distance(place1_coords, place2_coords):
    """
    Calculate distance between two places using Haversine formula.
    coords format: (latitude, longitude)
    Returns distance in km.
    """
    if place1_coords is None or place2_coords is None:
        return float('inf')  # Can't calculate, avoid this transition

    lat1, lon1 = place1_coords
    lat2, lon2 = place2_coords

    # Haversine formula
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
    """
    Convert distance to weight (closer = higher weight).
    max_distance: distance at which weight reaches min_weight.
    min_weight: minimum weight for far places (default 0.3).
    """
    if distance >= max_distance:
        return min_weight

    # Linear interpolation: 1.0 at distance=0, min_weight at max_distance
    return 1.0 - (distance / max_distance) * (1.0 - min_weight)


def get_time_weight(day_time, position_in_day):
    """
    Assign time-based weight based on position in daily itinerary.

    position_in_day: 0 (first), 1 (second), 2 (last)
    day_time: "morning", "afternoon", or "night"

    Returns weight between 0 and 1 (higher is better).
    """
    time_weights = {
        0: {"morning": 1.0, "afternoon": 0.6, "night": 0.2},
        1: {"morning": 0.7, "afternoon": 1.0, "night": 0.5},
        2: {"morning": 0.3, "afternoon": 0.7, "night": 1.0}
    }

    if position_in_day not in time_weights:
        return 0.5  # Default weight for unexpected positions

    day_time = day_time.lower() if day_time else "afternoon"
    return time_weights[position_in_day].get(day_time, 0.5)


def score_place(row, user_prefs, used_tags, position_in_day, last_place_coords=None):
    """
    Score a place considering:
    - Preference match
    - Popularity
    - Diversity penalty
    - Distance from last place (if applicable)
    - Time-based scoring based on position in day
    """
    try:
        pref_score = compute_preference_score(row, user_prefs)
        popularity = row.get("llama-3.3-70b-versatile_match_score", 50) / 100
        primary_tag = get_primary_tag(row, user_prefs)
        diversity = diversity_penalty(primary_tag, used_tags)

        # Time weighting based on position in day
        day_time = row.get("day_time", "afternoon")
        time_weight = get_time_weight(day_time, position_in_day)

        # Distance weighting (if we have a last place)
        distance_w = 1.0
        if last_place_coords is not None:
            try:
                current_coords = (row.get("latitude"), row.get("longitude"))
                distance = calculate_distance(last_place_coords, current_coords)
                distance_w = distance_weight(distance)
            except (TypeError, ValueError):
                distance_w = 1.0  # If can't calculate, neutral weight

        # Final scoring: preference is most important, time sequence matters
        final_score = (
            0.45 * pref_score +   # Preferences (highest weight)
            0.15 * popularity +   # Popularity
            0.20 * time_weight +  # Time efficiency
            0.10 * distance_w +   # Distance efficiency
            0.10 * diversity      # Diversity within day
        )

        return final_score

    except Exception as e:
        return 0.0


def rank_places(df, user_prefs, position_in_day, used_tags=None, last_place_coords=None):
    """
    Rank places based on score, considering:
    - Current day's used tags and last location
    - Position in day (affects time-based scoring)
    """
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

    except Exception as e:
        return df.copy()


def get_primary_tag(row, user_prefs):
    """Get the first matching preference tag for a place"""
    for tag in user_prefs:
        if tag in row and row[tag] == 1:
            return tag
    return None


def get_price_column(price_type="foreign"):
    """
    Get the appropriate price column name.
    price_type: "foreign" (default) or "egyptian"
    """
    price_columns = {
        "foreign": "foreigner price",
        "egyptian": "egyptian price"
    }
    return price_columns.get(price_type, "foreign price")


def build_day(candidates, budget, user_prefs, used_places, price_type="foreign"):
    """
    Build a single day's itinerary with:
    - Time-optimized sequence (morning, afternoon, night)
    - Diversity penalty applied within the day
    - Distance optimization between consecutive places
    - Budget constraint
    - Price type support (egyptian or foreign)
    """
    day = []
    used_tags = set()
    remaining_budget = budget
    last_place_coords = None

    current_candidates = candidates.copy()

    max_places_per_day = 3  # morning, afternoon, night
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

            primary_tag = get_primary_tag(row, user_prefs)
            day.append(row)
            used_tags.add(primary_tag)
            used_places.add(row["name"])

            if cost:
                remaining_budget -= cost

            try:
                last_place_coords = (row.get("latitude"), row.get("longitude"))
            except Exception:
                last_place_coords = None

            current_candidates = current_candidates[current_candidates["name"] != row["name"]]
            found = True
            break

        if not found:
            print(f"No valid place found for position {position}")
            break

    return day, remaining_budget


def build_itinerary(df, city, days, budget, user_prefs, country=None, price_type="foreign", child_rows=None):
    """
    Build a multi-day itinerary for a city (and optionally country) with optimized daily routes.

    Parameters
    ----------
    df : DataFrame
        The places dataframe.
    city : str
        City name to filter by.
    days : int
        Number of days for the itinerary.
    budget : float
        Total budget for the trip.
    user_prefs : set or list
        User preference tags.
    country : str, optional
        Country name to filter by (default: None).
    price_type : str
        Price column to use: "foreign" (default) or "egyptian".

    Returns
    -------
    dict
        Contains itinerary, remaining budget, and status message.
    """
    # --- Input validation (safe to catch errors here) ---
    if not isinstance(user_prefs, (set, list)):
        return {
            "success": False,
            "itinerary": [],
            "message": "User preferences must be a set or list."
        }

    user_prefs = set(user_prefs)

    if len(user_prefs) == 0:
        return {
            "success": False,
            "itinerary": [],
            "message": "Please select at least one preference category."
        }

    candidates = get_candidates(df, city, country)

    if candidates.empty:
        country_text = f" in {country}" if country else ""
        return {
            "success": False,
            "itinerary": [],
            "message": f"We don't have any places in {city}{country_text} yet. Check back soon!"
        }

    price_column = get_price_column(price_type)
    if price_column not in candidates.columns:
        price_type = "foreign"
        price_column = "foreigner price"

    # --- Build itinerary (errors here are real errors, caught separately) ---
    try:
        itinerary = []
        used_places = set()
        current_budget = budget

        for day_num in range(days):
            daily_pool = candidates[~candidates["name"].isin(used_places)]

            if daily_pool.empty:
                break

            day, current_budget = build_day(
                daily_pool,
                current_budget,
                user_prefs,
                used_places,
                price_type=price_type
            )

            if not day:
                break

            # Build structured day data
            day_places = []
            for place in day:
                name = place.get("name", "Unknown")
                cost_raw = place.get(price_column)
                cost = float(cost_raw) if cost_raw is not None else 0.0

                # Get children if applicable
                parent_value = place.get("parent", "")
                has_parent_word = isinstance(parent_value, str) and "parent" in parent_value.lower()
                children = []
                if has_parent_word and child_rows is not None and not child_rows.empty:
                    matched = child_rows[child_rows["parent"] == name]
                    children = matched["name"].tolist() if not matched.empty else []

                place_data = {
                    "name": name,
                    "day_time": place.get("day_time", "N/A"),
                    "cost": cost,
                    "category": place.get("llama-3.3-70b-versatile_category", "N/A"),
                    "website": str(place.get("website", "")) if str(place.get("website", "")) not in ("nan", "None", "") else None,
                    "children": children
                }
                day_places.append(place_data)

            itinerary.append({
                "day": day_num + 1,
                "places_count": len(day_places),
                "budget_remaining_after_day": round(current_budget, 2),
                "places": day_places
            })

    except Exception as e:
        return {
            "success": False,
            "itinerary": [],
            "message": f"Oops! We encountered an unexpected issue while planning your adventure. Please try again. (Error: {str(e)[:50]})"
        }

    # --- Success: determine message based on coverage ---
    total_places = len(candidates)
    visited_count = len(used_places)

    if visited_count == total_places:
        message = (
            f"Amazing! You've covered all {visited_count} incredible places we have in "
            f"{city}{' in ' + country if country else ''}! "
            f"Your journey is complete. Come back again for more adventures!"
        )
    else:
        message = (
            f"Itinerary created! You've explored {visited_count} wonderful places "
            f"out of {total_places} available."
        )

    return {
        "success": True,
        "message": message,
        "trip": {
            "city": city,
            "country": country,
            "days_planned": len(itinerary),
            "total_budget": budget,
            "remaining_budget": round(current_budget, 2),
            "spent_budget": round(budget - current_budget, 2),
            "visited_places": visited_count,
            "total_available_places": total_places,
            "itinerary": itinerary
        }
    }