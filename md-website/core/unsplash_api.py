"""
Unsplash API Integration
Automatic restaurant/food photo fetching based on cuisine type
"""

import requests
from django.conf import settings

UNSPLASH_ACCESS_KEY = getattr(settings, 'UNSPLASH_ACCESS_KEY', None)
UNSPLASH_API = "https://api.unsplash.com"


def search_place_photo(place_name, city, district=None, cuisine_type=None, category=None):
    """
    ULTRATHINK: Multi-stage contextual photo search
    
    Stage 1: Specific place search (e.g., "Nusr-Et Istanbul restaurant")
    Stage 2: Cuisine + location search (e.g., "Turkish restaurant Kadıköy Istanbul")
    Stage 3: Category generic search (e.g., "cafe interior ambiance")
    Stage 4: Fallback to default
    
    Args:
        place_name: Name of the place/restaurant
        city: City name
        district: Optional district/neighborhood
        cuisine_type: Type of cuisine (Italian, Turkish, etc.)
        category: Place category (restaurant, cafe, bar, etc.)
    
    Returns:
        dict with photo info including stage metadata
        None if all stages fail
    """
    if not UNSPLASH_ACCESS_KEY:
        print("⚠️ Unsplash API key not configured")
        return _get_default_photo()
    
    # Stage 1: Specific place search
    if place_name and city:
        # Truncate very long names (first 3 words max)
        name_parts = place_name.split()[:3]
        short_name = ' '.join(name_parts)
        query = f"{short_name} {city} restaurant"
        print(f"🔍 Stage 1: Searching '{query}'")
        
        result = _query_unsplash(query, per_page=3)
        if result:
            print(f"✅ Stage 1 SUCCESS: Found photo for '{place_name}'")
            result['search_stage'] = 1
            result['search_query'] = query
            return result
    
    # Stage 2: Cuisine + location search
    if cuisine_type and city:
        district_part = f"{district} " if district else ""
        query = f"{cuisine_type} restaurant {district_part}{city}"
        print(f"🔍 Stage 2: Searching '{query}'")
        
        result = _query_unsplash(query, per_page=5)
        if result:
            print(f"✅ Stage 2 SUCCESS: Found cuisine photo for '{cuisine_type}' in {city}")
            result['search_stage'] = 2
            result['search_query'] = query
            return result
    
    # Stage 3: Category generic search
    if category:
        print(f"🔍 Stage 3: Searching category '{category}'")
        result = get_category_photo(category)
        if result:
            print(f"✅ Stage 3 SUCCESS: Found category photo for '{category}'")
            result['search_stage'] = 3
            return result
    
    # Stage 4: Absolute fallback
    print("⚠️ Stage 4: Using default fallback photo")
    return _get_default_photo()


def _query_unsplash(query, per_page=5):
    """
    Internal helper to query Unsplash API
    
    Returns:
        dict with photo info or None if failed
    """
    url = f"{UNSPLASH_API}/search/photos"
    params = {
        'client_id': UNSPLASH_ACCESS_KEY,
        'query': query,
        'per_page': per_page,
        'orientation': 'landscape',
        'content_filter': 'high'
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 401:
            print("❌ Unsplash API authentication failed!")
            return None
        
        if response.status_code == 200:
            results = response.json().get('results', [])
            if results:
                photo = results[0]
                return {
                    'url': photo['urls']['regular'],
                    'url_small': photo['urls']['small'],
                    'url_full': photo['urls']['full'],
                    'photographer': photo['user']['name'],
                    'photographer_url': photo['user']['links']['html'],
                    'unsplash_id': photo['id'],
                    'alt_description': photo.get('alt_description', ''),
                    'color': photo.get('color', '#cccccc')
                }
    except Exception as e:
        print(f"Unsplash query error: {e}")
    
    return None


def _get_default_photo():
    """
    Fallback default photo when all searches fail
    """
    return {
        'url': 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4',  # Generic restaurant interior
        'url_small': 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=400',
        'photographer': 'Unsplash',
        'unsplash_id': 'default',
        'search_stage': 4,
        'search_query': 'default fallback'
    }


def search_restaurant_photo(cuisine_type, restaurant_name=None):
    """
    Get high-quality restaurant/food photo from Unsplash
    
    Args:
        cuisine_type: Type of cuisine (Italian, Japanese, Turkish, etc.)
        restaurant_name: Optional restaurant name for more specific results
    
    Returns:
        dict with url, photographer info
        None if not found or API key missing
    """
    if not UNSPLASH_ACCESS_KEY:
        print("⚠️ Unsplash API key not configured")
        return None
    
    # Build search query
    if restaurant_name:
        query = f"{restaurant_name} {cuisine_type} food"
    else:
        query = f"{cuisine_type} food restaurant dish"
    
    url = f"{UNSPLASH_API}/search/photos"
    params = {
        'client_id': UNSPLASH_ACCESS_KEY,
        'query': query,
        'per_page': 5,
        'orientation': 'landscape',
        'content_filter': 'high'  # Family-friendly content only
    }
    
    print(f"🔍 Unsplash query: {query}")  # Debug log
    
    try:
        response = requests.get(url, params=params, timeout=10)
        print(f"📡 Unsplash API status: {response.status_code}")  # Debug log
        
        if response.status_code == 401:
            print("❌ Unsplash API authentication failed! Check your Access Key (not Secret Key)")
            return None
        
        if response.status_code == 200:
            results = response.json().get('results', [])
            print(f"📸 Found {len(results)} photos from Unsplash")  # Debug log
            
            if results:
                photo = results[0]  # Take first result
                return {
                    'url': photo['urls']['regular'],  # Main size (1080px width)
                    'url_small': photo['urls']['small'],  # Thumbnail (400px)
                    'url_full': photo['urls']['full'],  # Full resolution
                    'photographer': photo['user']['name'],
                    'photographer_url': photo['user']['links']['html'],
                    'unsplash_id': photo['id'],
                    'alt_description': photo.get('alt_description', ''),
                    'color': photo.get('color', '#cccccc')  # Dominant color
                }
        else:
            print(f"⚠️ Unsplash API returned status {response.status_code}")
            print(f"Response: {response.text[:200]}")  # First 200 chars of response
    except Exception as e:
        print(f"Unsplash search error: {e}")
    
    return None


def get_multiple_photos(cuisine_type, count=5):
    """
    Get multiple photos for variety
    
    Args:
        cuisine_type: Cuisine type to search
        count: Number of photos to return (max 30)
    
    Returns:
        list of photo dicts
    """
    if not UNSPLASH_ACCESS_KEY:
        return []
    
    query = f"{cuisine_type} food restaurant"
    url = f"{UNSPLASH_API}/search/photos"
    params = {
        'client_id': UNSPLASH_ACCESS_KEY,
        'query': query,
        'per_page': min(count, 30),
        'orientation': 'landscape'
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            results = response.json().get('results', [])
            photos = []
            for photo in results:
                photos.append({
                    'url': photo['urls']['regular'],
                    'url_small': photo['urls']['small'],
                    'photographer': photo['user']['name'],
                    'unsplash_id': photo['id']
                })
            return photos
    except Exception as e:
        print(f"Unsplash multiple photos error: {e}")
    
    return []


def get_category_photo(category):
    """
    Get generic photo for place category (cafe, bar, etc.)
    
    Args:
        category: Place category (cafe, bar, restaurant, etc.)
    
    Returns:
        dict with photo info
    """
    category_queries = {
        'cafe': 'cozy cafe interior coffee',
        'bar': 'bar pub drinks cocktails',
        'restaurant': 'elegant restaurant interior dining',
        'fastfood': 'burger fries fast food',
        'bakery': 'bakery pastry bread',
        'dessert': 'dessert ice cream sweet',
    }
    
    query = category_queries.get(category, 'restaurant food')
    
    url = f"{UNSPLASH_API}/search/photos"
    params = {
        'client_id': UNSPLASH_ACCESS_KEY,
        'query': query,
        'per_page': 3,
        'orientation': 'landscape'
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            results = response.json().get('results', [])
            if results:
                photo = results[0]
                return {
                    'url': photo['urls']['regular'],
                    'url_small': photo['urls']['small'],
                    'photographer': photo['user']['name'],
                    'unsplash_id': photo['id']
                }
    except Exception as e:
        print(f"Unsplash category photo error: {e}")
    
    return None
