"""Feature selection is opt-in; legacy business labels are never rewritten."""
PROFILES = {
    "retail": {"name": "Retail / Supermarket", "features": []},
    "restaurant": {"name": "Restaurant / Café", "features": ["restaurant"]},
    "bar": {"name": "Bar / Nightclub", "features": ["restaurant"]},
    "hospitality": {"name": "Hotel / Hospitality", "features": ["restaurant", "hospitality"]},
    "pharmacy": {"name": "Pharmacy", "features": ["pharmacy"]},
    "wholesale": {"name": "Hardware / Wholesale", "features": ["wholesale"]},
    "general": {"name": "General Business", "features": []},
}


def infer_profile(label):
    normalized = str(label or "").strip().lower()
    aliases = {"retail": "retail", "supermarket": "retail", "restaurant": "restaurant", "café": "restaurant", "cafe": "restaurant", "bar": "bar", "nightclub": "bar", "hotel": "hospitality", "hospitality": "hospitality", "pharmacy": "pharmacy", "wholesale": "wholesale", "hardware": "wholesale"}
    return aliases.get(normalized, next((key for key, value in PROFILES.items() if value["name"].lower() == normalized), "general"))
