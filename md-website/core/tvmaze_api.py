"""
TVMaze API Integration
Free API for TV show metadata (no API key required!)
API Limit: None (unlimited free access)
"""

import requests

TVMAZE_BASE_URL = "https://api.tvmaze.com"


def search_tv_tvmaze(title):
    """
    Search for TV shows using TVMaze API
    
    Args:
        title: TV show title to search
    
    Returns:
        dict with TV show metadata
        None if not found
    """
    url = f"{TVMAZE_BASE_URL}/search/shows"
    params = {'q': title}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            results = response.json()
            
            if results:
                # Take first (best) result
                show = results[0].get('show', {})
                
                # Extract image URLs
                image = show.get('image', {})
                poster_url = image.get('medium') or image.get('original')
                backdrop_url = image.get('original')
                
                # Extract premiere year
                premiered = show.get('premiered', '')
                year = int(premiered[:4]) if premiered and len(premiered) >= 4 else None
                
                return {
                    'title': show.get('name', title),
                    'original_title': show.get('name', ''),
                    'poster_url': poster_url,
                    'backdrop_url': backdrop_url,
                    'overview': strip_html(show.get('summary', '')),
                    'first_air_date': premiered,
                    'year': year,
                    'rating': show.get('rating', {}).get('average', 0) or 0,
                    'tvmaze_id': show.get('id'),
                    'status': show.get('status', ''),
                    'network': show.get('network', {}).get('name', '') if show.get('network') else '',
                    'genre': ', '.join(show.get('genres', [])),
                }
        else:
            print(f"TVMaze API error: {response.status_code}")
    except Exception as e:
        print(f"TVMaze search error: {e}")
    
    return None


def search_shows_tvmaze(query):
    """
    Search for multiple TV shows by query
    
    Args:
        query: Search query string
    
    Returns:
        list of TV show results
    """
    url = f"{TVMAZE_BASE_URL}/search/shows"
    params = {'q': query}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            results = response.json()
            
            shows = []
            for item in results[:10]:  # Top 10 results
                show = item.get('show', {})
                image = show.get('image', {})
                premiered = show.get('premiered', '')
                year = int(premiered[:4]) if premiered and len(premiered) >= 4 else None
                
                shows.append({
                    'media_type': 'tv',
                    'tvmaze_id': show.get('id'),
                    'title': show.get('name', ''),
                    'poster_url': image.get('medium') or image.get('original'),
                    'release_year': premiered[:4] if premiered else '',
                    'year': year,
                    'rating': show.get('rating', {}).get('average', 0) or 0,
                    'overview': strip_html(show.get('summary', ''))[:150] + '...' if show.get('summary') else '',
                })
            
            return shows
        else:
            print(f"TVMaze search API error: {response.status_code}")
    except Exception as e:
        print(f"TVMaze multi-search error: {e}")
    
    return []


def get_tv_details_tvmaze(tvmaze_id):
    """
    Get detailed TV show info including episodes
    
    Args:
        tvmaze_id: TVMaze show ID
    
    Returns:
        dict with detailed TV show information
    """
    url = f"{TVMAZE_BASE_URL}/shows/{tvmaze_id}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            show = response.json()
            
            # Get episode list to count total episodes
            episodes_url = f"{TVMAZE_BASE_URL}/shows/{tvmaze_id}/episodes"
            episodes_response = requests.get(episodes_url, timeout=10)
            total_episodes = 0
            
            if episodes_response.status_code == 200:
                episodes = episodes_response.json()
                total_episodes = len(episodes)
            
            image = show.get('image', {})
            premiered = show.get('premiered', '')
            
            return {
                'title': show.get('name', ''),
                'year': int(premiered[:4]) if premiered and len(premiered) >= 4 else None,
                'rating': show.get('rating', {}).get('average', 0) or 0,
                'poster_url': image.get('medium') or image.get('original'),
                'backdrop_url': image.get('original'),
                'overview': strip_html(show.get('summary', '')),
                'status': show.get('status', ''),
                'network': show.get('network', {}).get('name', '') if show.get('network') else '',
                'genre': ', '.join(show.get('genres', [])),
                'total_episodes': total_episodes,
                'tvmaze_id': show.get('id'),
            }
        else:
            print(f"TVMaze details API error: {response.status_code}")
    except Exception as e:
        print(f"TVMaze details error: {e}")
    
    return None


def strip_html(text):
    """
    Remove HTML tags from text
    TVMaze returns summaries with HTML tags
    
    Args:
        text: HTML text string
    
    Returns:
        Plain text without HTML tags
    """
    if not text:
        return ''
    
    import re
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', text)
    return clean.strip()
