from flask import Blueprint, request, jsonify, flash, current_app
from utils import get_setting
import json
from datetime import datetime
import requests
import time

igdb_bp = Blueprint('igdb', __name__)

_IGDB_ACCESS_TOKEN = None
_IGDB_TOKEN_EXPIRY = 0

def construct_igdb_image_url(image_id, size="cover_big"):
    """Constructs a full HTTPS URL for an IGDB image."""
    if image_id:
        return f"https://images.igdb.com/igdb/image/upload/t_{size}/{image_id}.jpg"
    return None

def _get_igdb_token(client_id, client_secret):
    """Get or refresh IGDB access token."""
    global _IGDB_ACCESS_TOKEN, _IGDB_TOKEN_EXPIRY
    
    if _IGDB_ACCESS_TOKEN and time.time() < _IGDB_TOKEN_EXPIRY - 60:
        return _IGDB_ACCESS_TOKEN
    
    if not client_id or not client_secret:
        raise ValueError("IGDB API credentials are not configured in settings.")
    
    try:
        response = requests.post('https://id.twitch.tv/oauth2/token', 
                               params={
                                   'client_id': client_id,
                                   'client_secret': client_secret,
                                   'grant_type': 'client_credentials'
                               },
                               timeout=10)
        response.raise_for_status()
        token_data = response.json()
        
        _IGDB_ACCESS_TOKEN = token_data['access_token']
        _IGDB_TOKEN_EXPIRY = time.time() + token_data['expires_in']
        
        current_app.logger.info("Successfully obtained new IGDB token")
        return _IGDB_ACCESS_TOKEN
        
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Failed to get IGDB token: {e}")
        raise

def _search_igdb_games(game_title, system_name, client_id, client_secret):
    """Search IGDB for games matching the title and system."""
    try:
        token = _get_igdb_token(client_id, client_secret)
    except Exception as e:
        current_app.logger.error(f"Token error: {e}")
        return []
    
    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json'
    }
    
    sanitized_title = game_title.replace('"', '').strip()
    
    platform_mapping = {
        'Nintendo Entertainment System': 'NES',
        'Super Nintendo': 'Super Nintendo Entertainment System',
        'Game Boy': 'Game Boy',
        'Game Boy Color': 'Game Boy Color',
        'Game Boy Advance': 'Game Boy Advance',
        'Sega Genesis': 'Sega Mega Drive/Genesis',
        'Nintendo 64': 'Nintendo 64',
        'PlayStation 1': 'PlayStation',
    }
    
    igdb_platform = platform_mapping.get(system_name, system_name)
    
    query = f'''
    search "{sanitized_title}";
    fields name, summary, genres.name, first_release_date, 
           involved_companies.company.name, involved_companies.developer, involved_companies.publisher,
           cover.image_id, platforms.name;
    limit 10;
    '''
    
    try:
        response = requests.post('https://api.igdb.com/v4/games', 
                               headers=headers, 
                               data=query.encode('utf-8'),
                               timeout=10)
        response.raise_for_status()
        games = response.json()
        
        current_app.logger.info(f"IGDB search for '{sanitized_title}' returned {len(games)} results")
        return games
        
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"IGDB API request failed: {e}")
        return []

@igdb_bp.route('/igdb_search', methods=['GET'])
def igdb_search():
    query = request.args.get('query', '').strip()
    system = request.args.get('system', '').strip()
    
    if not query:
        return jsonify([])

    client_id = get_setting('igdb_client_id')
    client_secret = get_setting('igdb_client_secret')

    if not client_id or not client_secret or client_id == 'YOUR_IGDB_CLIENT_ID':
        current_app.logger.warning("IGDB credentials not set in Settings")
        return jsonify({"error": "IGDB credentials not set."}), 400

    try:
        games = _search_igdb_games(query, system, client_id, client_secret)
        
        formatted_results = []
        for game in games:
            metadata = {}
            if 'genres' in game and game['genres']:
                metadata['genre'] = ', '.join([g['name'] for g in game['genres']])
            
            if 'first_release_date' in game:
                metadata['release_year'] = time.gmtime(game['first_release_date']).tm_year
            
            if 'summary' in game:
                metadata['description'] = game['summary']
            
            developers = []
            publishers = []
            if 'involved_companies' in game:
                for ic in game['involved_companies']:
                    if 'company' in ic and 'name' in ic['company']:
                        if ic.get('developer'):
                            developers.append(ic['company']['name'])
                        if ic.get('publisher'):
                            publishers.append(ic['company']['name'])
            
            if developers:
                metadata['developer'] = ", ".join(developers)
            if publishers:
                metadata['publisher'] = ", ".join(publishers)
            
            cover_image_id = game.get('cover', {}).get('image_id')
            cover_url = construct_igdb_image_url(cover_image_id)
            
            platforms = []
            if 'platforms' in game:
                platforms = [p.get('name', '') for p in game['platforms'] if p.get('name')]
            platform_str = ', '.join(platforms) if platforms else system
            
            result_data = {
                'name': game.get('name', query),
                'cover_url': cover_url,
                'image_id': cover_image_id,  # ADDED: image_id for the front-end to use
                'platforms': platform_str,
                'release_date': metadata.get('release_year', 'N/A'),
                'full_metadata': metadata
            }
            
            formatted_results.append(result_data)
        
        current_app.logger.info(f"Returning {len(formatted_results)} formatted results")
        return jsonify(formatted_results)
        
    except Exception as e:
        current_app.logger.error(f"Error in IGDB search: {e}")
        return jsonify({"error": f"Search failed: {str(e)}"}), 500

@igdb_bp.route('/igdb_set_cover', methods=['POST'])
def igdb_set_cover():
    data = request.json
    game_id = data.get('game_id')
    image_id = data.get('image_id')

    if not game_id or not image_id:
        return jsonify({"error": "Missing game_id or image_id"}), 400

    try:
        from scanner.core import download_and_set_cover_image
        
        def web_log(message, tag=None):
            current_app.logger.info(f"[{tag or 'INFO'}] {message}")
        
        full_igdb_url = construct_igdb_image_url(image_id)
        new_path = download_and_set_cover_image(game_id, full_igdb_url, web_log)
        return jsonify({"success": True, "new_path": new_path})
        
    except Exception as e:
        current_app.logger.error(f"Error setting cover from IGDB: {e}")
        return jsonify({"error": str(e)}), 500