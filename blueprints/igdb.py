# blueprints/igdb.py
from flask import Blueprint, request, jsonify, flash, current_app
from utils import get_setting
from scanner.core import fetch_igdb_data, download_and_set_cover_image
import json
from datetime import datetime

igdb_bp = Blueprint('igdb', __name__)

def construct_igdb_image_url(image_id, size="cover_big"):
    """Constructs a full HTTPS URL for an IGDB image."""
    if image_id:
        return f"https://images.igdb.com/igdb/image/upload/t_{size}/{image_id}.jpg"
    return None

@igdb_bp.route('/igdb_search', methods=['GET'])
def igdb_search():
    query = request.args.get('query', '').strip()
    system = request.args.get('system', '').strip()
    if not query or not system:
        return jsonify([])

    client_id = get_setting('igdb_client_id')
    client_secret = get_setting('igdb_client_secret')

    if not client_id or not client_secret or client_id == 'YOUR_IGDB_CLIENT_ID':
        flash("IGDB credentials not set in Settings.", "warning")
        return jsonify({"error": "IGDB credentials not set."}), 400

    # Use the unified core function for the API call
    metadata, image_urls = fetch_igdb_data(query, system, lambda m, t=None: print(f"[{t or 'INFO'}] {m}"), client_id, client_secret)

    # The web UI expects a specific format, so we reformat the results here
    formatted_results = []
    if metadata:
        # Since the API returns one best match, we create a list with that one result
        # This structure is what the 'edit_game.html' JavaScript expects
        result_data = {
            'name': metadata.get('developer', query), # The JS uses 'name' for the developer field
            'cover_url': image_urls[0] if image_urls else None,
            'platforms': system,
            'release_date': metadata.get('release_year', 'N/A'),
            # Pass along all data for the edit form to use
            'full_metadata': metadata,
            'image_urls': image_urls
        }
        
        # The JS expects a list of results, even if there's only one
        formatted_results.append(result_data)

    return jsonify(formatted_results)

@igdb_bp.route('/igdb_set_cover', methods=['POST'])
def igdb_set_cover():
    data = request.json
    game_id = data.get('game_id')
    image_url = data.get('image_url')

    if not game_id or not image_url:
        return jsonify({"error": "Missing game_id or image_url"}), 400

    try:
        # Use the unified core function to download the image and update the DB
        new_path = download_and_set_cover_image(game_id, image_url, lambda m, t=None: print(f"[{t or 'INFO'}] {m}"))
        return jsonify({"success": True, "new_path": new_path})
    except Exception as e:
        print(f"Error setting cover from IGDB: {e}")
        return jsonify({"error": str(e)}), 500
