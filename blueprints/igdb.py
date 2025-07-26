import os
import json
import requests
from datetime import datetime, timedelta

from flask import Blueprint, request, redirect, url_for, flash, current_app

from utils import get_setting # <--- NEW IMPORT

igdb_bp = Blueprint('igdb', __name__)

# IGDB Token Management Functions - These are internal to the IGDB blueprint's logic
def _get_igdb_access_token():
    # Prioritize settings from settings.json, fall back to config.py if not found
    client_id = get_setting('igdb_client_id', current_app.config['IGDB_CLIENT_ID'])
    client_secret = get_setting('igdb_client_secret', current_app.config['IGDB_CLIENT_SECRET'])

    # Validate that actual (non-placeholder) credentials exist
    if not client_id or not client_secret or \
       client_id == 'YOUR_IGDB_CLIENT_ID' or \
       client_secret == 'YOUR_IGDB_CLIENT_SECRET':
        flash("IGDB Client ID or Client Secret not set. Please go to Settings to configure.", "warning")
        return None

    token_data = {}
    token_file = current_app.config['IGDB_TOKEN_FILE']
    if os.path.exists(token_file):
        with open(token_file, 'r') as f:
            token_data = json.load(f)

    if token_data and 'access_token' in token_data and 'expires_at' in token_data:
        if datetime.now() < datetime.fromtimestamp(token_data['expires_at']):
            return token_data['access_token']

    try:
        url = "https://id.twitch.tv/oauth2/token"
        payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'client_credentials'
        }
        response = requests.post(url, data=payload)
        response.raise_for_status()
        
        new_token_data = response.json()
        access_token = new_token_data['access_token']
        expires_in = new_token_data['expires_in']
        
        expires_at = datetime.now() + timedelta(seconds=expires_in - 300) # 5 min buffer
        
        token_data = {
            'access_token': access_token,
            'expires_at': expires_at.timestamp()
        }
        
        with open(token_file, 'w') as f:
            json.dump(token_data, f, indent=4)
        
        return access_token
    except requests.exceptions.RequestException as e:
        flash(f"Error getting IGDB access token. Check credentials and internet connection: {e}", 'error')
        print(f"Error getting IGDB access token: {e}")
        return None

def _igdb_api_request(endpoint, query_body):
    access_token = _get_igdb_access_token()
    if not access_token:
        return None

    # Prioritize settings from settings.json, fall back to config.py if not found
    client_id = get_setting('igdb_client_id', current_app.config['IGDB_CLIENT_ID'])

    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json'
    }
    url = f"https://api.igdb.com/v4/{endpoint}"
    
    try:
        response = requests.post(url, headers=headers, data=query_body)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        flash(f"Error making IGDB API request. Check console for details.", 'error')
        print(f"Error making IGDB API request to {endpoint}: {e}")
        return None

# IGDB Routes (remain the same)
@igdb_bp.route('/igdb_search', methods=['GET'])
def igdb_search():
    # ... (rest of function remains the same) ...
    query = request.args.get('query', '').strip()
    if not query:
        return json.dumps([])

    query_body = f'search "{query}"; fields name, cover.url, platforms.name, first_release_date; limit 10;'
    results = _igdb_api_request('games', query_body)

    formatted_results = []
    if results:
        for game in results:
            cover_url = None
            if 'cover' in game and 'url' in game['cover']:
                cover_url = f"https:{game['cover']['url']}"
            
            platforms = "Unknown Platform"
            if 'platforms' in game:
                platform_names = [p['name'] for p in game['platforms'] if 'name' in p]
                if platform_names:
                    platforms = ", ".join(platform_names)

            formatted_results.append({
                'id': game['id'],
                'name': game['name'],
                'cover_url': cover_url,
                'platforms': platforms,
                'release_date': datetime.fromtimestamp(game['first_release_date']).year if 'first_release_date' in game else 'N/A'
            })
    return json.dumps(formatted_results)

@igdb_bp.route('/igdb_cover/<int:igdb_game_id>')
def igdb_cover(igdb_game_id):
    query_body = f'fields url; where game = {igdb_game_id}; limit 1;'
    results = _igdb_api_request('covers', query_body)
    
    if results and results[0] and 'url' in results[0]:
        return redirect(f"https:{results[0]['url']}")
    return redirect(url_for('static', filename='placeholder.png'))