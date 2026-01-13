"""
OMDb (Open Movie Database) API Integration
Free alternative to TMDB for movie metadata
API Limit: 1,000 requests/day (free tier)
"""

import requests
from django.conf import settings

OMDB_API_KEY = getattr(settings, 'OMDB_API_KEY', None)
OMDB_BASE_URL = "http://www.omdbapi.com/"


def search_movie_omdb(title, year=None):
    """
    Search for movie using OMDb API
    
    Args:
        title: Movie title to search
        year: Optional release year for better matching
    
    Returns:
        dict with title, poster_url, overview, etc.
        None if not found or API key missing
    """
    if not OMDB_API_KEY:
        print("⚠️ OMDb API key not configured")
        return None
    
    params = {
        'apikey': OMDB_API_KEY,
        't': title,  # Title search
        'type': 'movie',
        'plot': 'full'
    }
    
    if year:
        params['y'] = year
    
    try:
        response = requests.get(OMDB_BASE_URL, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            
            # Check if movie was found
            if data.get('Response') == 'True':
                return {
                    'title': data.get('Title', title),
                    'original_title': data.get('Title', ''),
                    'poster_url': data.get('Poster') if data.get('Poster') != 'N/A' else None,
                    'backdrop_url': None,  # OMDb doesn't provide backdrops
                    'overview': data.get('Plot', ''),
                    'release_date': data.get('Released', ''),
                    'year': int(data.get('Year', '0')) if data.get('Year', '').isdigit() else None,
                    'rating': float(data.get('imdbRating', '0')) if data.get('imdbRating') != 'N/A' else 0,
                    'imdb_id': data.get('imdbID', ''),
                    'genre': data.get('Genre', ''),
                    'runtime': data.get('Runtime', ''),
                    'director': data.get('Director', ''),
                    'actors': data.get('Actors', ''),
                    'metascore': data.get('Metascore', ''),
                }
            else:
                print(f"OMDb: Movie not found - {data.get('Error', 'Unknown error')}")
        else:
            print(f"OMDb API error: {response.status_code}")
    except Exception as e:
        print(f"OMDb search error: {e}")
    
    return None


def search_movies_omdb(query):
    """
    Search for multiple movies by query
    
    Args:
        query: Search query string
    
    Returns:
        list of movie results
    """
    if not OMDB_API_KEY:
        return []
    
    params = {
        'apikey': OMDB_API_KEY,
        's': query,  # Search query
        'type': 'movie'
    }
    
    try:
        response = requests.get(OMDB_BASE_URL, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            
            if data.get('Response') == 'True':
                results = []
                for item in data.get('Search', [])[:10]:  # Top 10 results
                    results.append({
                        'media_type': 'movie',
                        'imdb_id': item.get('imdbID', ''),
                        'title': item.get('Title', ''),
                        'poster_url': item.get('Poster') if item.get('Poster') != 'N/A' else None,
                        'release_year': item.get('Year', ''),
                        'year': int(item.get('Year', '0')) if item.get('Year', '').isdigit() else None,
                    })
                return results
            else:
                print(f"OMDb search: {data.get('Error', 'No results')}")
        else:
            print(f"OMDb API error: {response.status_code}")
    except Exception as e:
        print(f"OMDb multi-search error: {e}")
    
    return []


def get_movie_details_omdb(imdb_id):
    """
    Get detailed movie info by IMDb ID
    
    Args:
        imdb_id: IMDb ID (e.g., 'tt1375666')
    
    Returns:
        dict with detailed movie information
    """
    if not OMDB_API_KEY:
        return None
    
    params = {
        'apikey': OMDB_API_KEY,
        'i': imdb_id,  # IMDb ID
        'plot': 'full'
    }
    
    try:
        response = requests.get(OMDB_BASE_URL, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            
            if data.get('Response') == 'True':
                return {
                    'title': data.get('Title', ''),
                    'year': int(data.get('Year', '0')) if data.get('Year', '').isdigit() else None,
                    'rating': float(data.get('imdbRating', '0')) if data.get('imdbRating') != 'N/A' else 0,
                    'poster_url': data.get('Poster') if data.get('Poster') != 'N/A' else None,
                    'overview': data.get('Plot', ''),
                    'genre': data.get('Genre', ''),
                    'director': data.get('Director', ''),
                    'actors': data.get('Actors', ''),
                    'runtime': data.get('Runtime', ''),
                    'imdb_id': data.get('imdbID', ''),
                }
        else:
            print(f"OMDb details API error: {response.status_code}")
    except Exception as e:
        print(f"OMDb details error: {e}")
    
    return None
