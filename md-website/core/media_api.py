"""
Unified Media API - Hybrid Approach
Uses OMDb for movies and TVMaze for TV shows as alternatives to TMDB

This provides backward compatibility while using free, accessible APIs
"""

from .omdb_api import search_movie_omdb, search_movies_omdb, get_movie_details_omdb
from .tvmaze_api import search_tv_tvmaze, search_shows_tvmaze, get_tv_details_tvmaze


def search_movie(title, year=None):
    """
    Search for movie using OMDb API
    
    Args:
        title: Movie title to search
        year: Optional release year
    
    Returns:
        dict with movie metadata (OMDb format)
    """
    return search_movie_omdb(title, year)


def search_tv_series(title, year=None):
    """
    Search for TV series using TVMaze API
    
    Args:
        title: Series title to search
        year: Optional first air year (not used by TVMaze)
    
    Returns:
        dict with TV show metadata (TVMaze format)
    """
    return search_tv_tvmaze(title)


def search_multi(query, year=None):
    """
    Hybrid search using OMDb + TVMaze
    Searches both movies (OMDb) and TV shows (TVMaze) simultaneously
    
    Args:
        query: Search query string
        year: Optional year filter
    
    Returns:
        list of results with unified format
    """
    results = []
    
    # Search movies via OMDb
    try:
        movie_results = search_movies_omdb(query)
        results.extend(movie_results)
    except Exception as e:
        print(f"OMDb multi-search error: {e}")
    
    # Search TV shows via TVMaze
    try:
        tv_results = search_shows_tvmaze(query)
        results.extend(tv_results)
    except Exception as e:
        print(f"TVMaze multi-search error: {e}")
    
    # Sort by relevance (prioritize higher ratings)
    results.sort(key=lambda x: x.get('rating', 0), reverse=True)
    
    return results[:15]  # Return top 15 combined results


def get_movie_details(identifier, id_type='imdb'):
    """
    Get detailed movie information
    
    Args:
        identifier: IMDb ID or title
        id_type: 'imdb' or 'title'
    
    Returns:
        dict with detailed movie info
    """
    if id_type == 'imdb':
        return get_movie_details_omdb(identifier)
    else:
        return search_movie_omdb(identifier)


def get_tv_details(tvmaze_id):
    """
    Get detailed TV show information including episodes
    
    Args:
        tvmaze_id: TVMaze show ID
    
    Returns:
        dict with detailed TV info
    """
    return get_tv_details_tvmaze(tvmaze_id)


# Backward compatibility aliases
def get_tv_series_details(tvmaze_id):
    """Alias for backward compatibility"""
    return get_tv_details(tvmaze_id)
