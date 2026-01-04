"""
TMDB (The Movie Database) API Integration
Automatic poster and metadata fetching for movies, TV series, and books
"""

import requests
from django.conf import settings

TMDB_API_KEY = getattr(settings, 'TMDB_API_KEY', None)
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
TMDB_BACKDROP_BASE = "https://image.tmdb.org/t/p/original"


def search_movie(title, year=None):
    """
    Search for movie and return poster + metadata
    
    Args:
        title: Movie title to search
        year: Optional release year for better matching
    
    Returns:
        dict with title, poster_url, backdrop_url, overview, etc.
        None if not found or API key missing
    """
    if not TMDB_API_KEY:
        print("⚠️ TMDB API key not configured")
        return None
    
    url = f"{TMDB_BASE_URL}/search/movie"
    params = {
        'api_key': TMDB_API_KEY,
        'query': title,
        'language': 'tr-TR',
        'include_adult': False
    }
    
    if year:
        params['year'] = year
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            results = response.json().get('results', [])
            if results:
                movie = results[0]  # Take first result
                return {
                    'title': movie.get('title', title),
                    'original_title': movie.get('original_title', ''),
                    'poster_url': f"{TMDB_IMAGE_BASE}{movie['poster_path']}" if movie.get('poster_path') else None,
                    'backdrop_url': f"{TMDB_BACKDROP_BASE}{movie['backdrop_path']}" if movie.get('backdrop_path') else None,
                    'overview': movie.get('overview', ''),
                    'release_date': movie.get('release_date', ''),
                    'rating': movie.get('vote_average', 0),
                    'tmdb_id': movie['id'],
                    'genre_ids': movie.get('genre_ids', [])
                }
        else:
            print(f"TMDB API error: {response.status_code}")
    except Exception as e:
        print(f"TMDB search error: {e}")
    
    return None


def search_tv_series(title, year=None):
    """
    Search for TV series and return poster + metadata
    
    Args:
        title: Series title to search
        year: Optional first air year
    
    Returns:
        dict with title, poster_url, backdrop_url, overview, etc.
        None if not found
    """
    if not TMDB_API_KEY:
        return None
    
    url = f"{TMDB_BASE_URL}/search/tv"
    params = {
        'api_key': TMDB_API_KEY,
        'query': title,
        'language': 'tr-TR',
        'include_adult': False
    }
    
    if year:
        params['first_air_date_year'] = year
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            results = response.json().get('results', [])
            if results:
                series = results[0]
                
                # Get detailed info for episode count
                tmdb_id = series['id']
                details = get_tv_details(tmdb_id)
                
                return {
                    'title': series.get('name', title),
                    'original_title': series.get('original_name', ''),
                    'poster_url': f"{TMDB_IMAGE_BASE}{series['poster_path']}" if series.get('poster_path') else None,
                    'backdrop_url': f"{TMDB_BACKDROP_BASE}{series['backdrop_path']}" if series.get('backdrop_path') else None,
                    'overview': series.get('overview', ''),
                    'first_air_date': series.get('first_air_date', ''),
                    'rating': series.get('vote_average', 0),
                    'tmdb_id': tmdb_id,
                    'total_episodes': details.get('total_episodes', 0) if details else 0,
                    'total_seasons': details.get('total_seasons', 0) if details else 0,
                }
    except Exception as e:
        print(f"TMDB TV search error: {e}")
    
    return None


def get_tv_details(tmdb_id):
    """
    Get detailed TV series info including episode count
    
    Args:
        tmdb_id: TMDB series ID
    
    Returns:
        dict with total_episodes, total_seasons, etc.
    """
    if not TMDB_API_KEY:
        return None
    
    url = f"{TMDB_BASE_URL}/tv/{tmdb_id}"
    params = {
        'api_key': TMDB_API_KEY,
        'language': 'tr-TR'
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                'total_episodes': data.get('number_of_episodes', 0),
                'total_seasons': data.get('number_of_seasons', 0),
                'status': data.get('status', ''),
                'in_production': data.get('in_production', False)
            }
    except Exception as e:
        print(f"TMDB TV details error: {e}")
    
    return None


def search_multi(query, year=None):
    """
    Search across movies and TV shows simultaneously
    
    Returns:
        list of results with type indicator (movie/tv)
    """
    if not TMDB_API_KEY:
        return []
    
    url = f"{TMDB_BASE_URL}/search/multi"
    params = {
        'api_key': TMDB_API_KEY,
        'query': query,
        'language': 'tr-TR',
        'include_adult': False
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            results = response.json().get('results', [])
            
            # Filter to only movies and TV shows
            filtered = []
            for item in results[:10]:  # Limit to top 10
                if item.get('media_type') in ['movie', 'tv']:
                    result = {
                        'media_type': item['media_type'],
                        'tmdb_id': item['id'],
                        'title': item.get('title') or item.get('name', ''),
                        'poster_url': f"{TMDB_IMAGE_BASE}{item['poster_path']}" if item.get('poster_path') else None,
                        'release_year': (item.get('release_date') or item.get('first_air_date', ''))[:4],
                        'rating': item.get('vote_average', 0),
                        'overview': item.get('overview', '')[:150] + '...'  # Truncate
                    }
                    filtered.append(result)
            
            return filtered
    except Exception as e:
        print(f"TMDB multi search error: {e}")
    
    return []
