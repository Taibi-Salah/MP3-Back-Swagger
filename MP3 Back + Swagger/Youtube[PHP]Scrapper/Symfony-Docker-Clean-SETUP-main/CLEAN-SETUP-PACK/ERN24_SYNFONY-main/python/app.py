from flask import Flask, request, jsonify, Blueprint, send_file
from ytmusicapi import YTMusic
import mysql.connector
import os
import logging
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
import requests
import socket
from datetime import datetime
import stat
from flask_swagger_ui import get_swaggerui_blueprint
import yaml

app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

# Add this line to create a Blueprint with a URL prefix
api = Blueprint('api', __name__, url_prefix='/api')

# Initialize YTMusic
ytmusic = YTMusic()

# Database configuration (hardcoded)
DB_HOST = 'immobase'    # Service name defined in docker-compose.yml
DB_PORT = 3306           # **Internal Docker network port**
DB_NAME = 'immo'
DB_USER = 'immouser'
DB_PASSWORD = 'immouser'

def get_db_connection():
    app.logger.debug(f"Attempting to connect to database: {DB_HOST}:{DB_PORT}")
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset='utf8mb4',
            collation='utf8mb4_general_ci'
        )
        app.logger.debug("Database connection successful")
        return conn
    except mysql.connector.Error as e:
        app.logger.error(f"Database connection failed: {str(e)}")
        raise

def get_ytmusic_info(title):
    try:
        search_results = ytmusic.search(title, filter='songs', limit=1)
        if search_results:
            song_info = search_results[0]
            return {
                'title': song_info['title'],
                'artist_name': ', '.join(artist['name'] for artist in song_info['artists']),
                'artist_id': song_info['artists'][0]['id'] if song_info['artists'] else None,
                'album_name': song_info['album']['name'] if 'album' in song_info else None,
                'album_id': song_info['album']['id'] if 'album' in song_info else None,
                'duration': song_info.get('duration_seconds'),
                'year': song_info['album']['year'] if 'album' in song_info and 'year' in song_info['album'] else None,
                'isExplicit': song_info.get('isExplicit', False),
                'thumbnails': song_info.get('thumbnails', []),
                'artist_thumb_url': song_info['artists'][0].get('thumbnails', [{}])[0].get('url') if song_info['artists'] else None
            }
    except Exception as e:
        app.logger.error(f"Error fetching YTMusic info: {str(e)}")
    return {}

SHARED_MP3_PATH = '/var/www/html/MP3_MUSICS'

def get_mp3_info(file_path):
    try:
        # Use the shared volume path
        adjusted_path = os.path.join(SHARED_MP3_PATH, os.path.basename(file_path))
        app.logger.info(f"Attempting to read MP3 file: {adjusted_path}")
        
        if not os.path.exists(adjusted_path):
            app.logger.error(f"File not found: {adjusted_path}")
            app.logger.info(f"Directory contents: {os.listdir(SHARED_MP3_PATH)}")
            return {}
        
        audio = MP3(adjusted_path, ID3=ID3)
        return {
            'duration': audio.info.length,
            'artist_name': audio.get('TPE1', [''])[0],
            'album_name': audio.get('TALB', [''])[0],
            'year': str(audio.get('TDRC', [''])[0]),
            'genre': audio.get('TCON', [''])[0],
            'track_number': str(audio.get('TRCK', [''])[0]),
        }
    except Exception as e:
        app.logger.error(f"Error reading MP3 metadata: {str(e)}")
    return {}

@api.route('/latest_mp3', methods=['GET'])
def latest_mp3():
    try:
        app.logger.info(f"Searching for MP3 files in: {SHARED_MP3_PATH}")
        mp3_files = [f for f in os.listdir(SHARED_MP3_PATH) if f.endswith('.mp3')]
        if not mp3_files:
            return jsonify({"error": "No MP3 files found"}), 404
        
        latest_file = max(mp3_files, key=lambda f: os.path.getmtime(os.path.join(SHARED_MP3_PATH, f)))
        file_path = os.path.join(SHARED_MP3_PATH, latest_file)
        
        app.logger.info(f"Latest MP3 file: {file_path}")
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        app.logger.error(f"Error in latest_mp3: {str(e)}")
        return jsonify({"error": str(e)}), 500

def update_db_with_new_info(data):
    # Implement database update logic here
    pass


@api.route('/create_artist', methods=['POST'])
def create_artist():
    try:
        # Fetch latest MP3 data
        response = requests.get('http://localhost:5000/api/latest_mp3')
        response.raise_for_status()
        latest_mp3_data = response.json()
        
        if not latest_mp3_data:
            return jsonify({'error': 'No MP3 data available'}), 404
        
        # Use the correct path for the MP3 file
        mp3_file_path = os.path.join(SHARED_MP3_PATH, latest_mp3_data['mp3_file'])
        
        # Log file path and check if it exists
        app.logger.info(f"Checking MP3 file: {mp3_file_path}")
        if os.path.exists(mp3_file_path):
            app.logger.info(f"File exists: {mp3_file_path}")
        else:
            app.logger.error(f"File not found: {mp3_file_path}")
            # Log directory contents
            app.logger.info(f"Directory contents of {SHARED_MP3_PATH}: {os.listdir(SHARED_MP3_PATH)}")
            return jsonify({'error': 'MP3 file not found'}), 404
        
        # Prepare artist data
        artist_data = {
            "@context": "/api/contexts/Artist",
            "@type": "Artist",
            "name": latest_mp3_data['artist_name'],
            "biography": "",  # You might want to fetch this from another source
            "imagePath": latest_mp3_data.get('artist_thumb_url') or (latest_mp3_data.get('thumbnails', [{}])[-1].get('url') if latest_mp3_data.get('thumbnails') else None),
            "albums": [{
                "@context": "/api/contexts/Album",
                "@type": "Album",
                "title": latest_mp3_data['album_name'],
                "imagePath": latest_mp3_data.get('album_cover_url') or (latest_mp3_data.get('thumbnails', [{}])[-1].get('url') if latest_mp3_data.get('thumbnails') else None),
                "genre": [{"@type": "Genre", "label": latest_mp3_data['genre']}] if latest_mp3_data.get('genre') else [],
                "songs": [{
                    "@context": "/api/contexts/Song",
                    "@type": "Song",
                    "title": latest_mp3_data['title'],
                    "filePath": mp3_file_path,
                    "duration": latest_mp3_data['duration']
                }],
                "releaseDate": f"{latest_mp3_data['year']}-01-01T00:00:00Z" if latest_mp3_data.get('year') else datetime.now().isoformat(),
                "isActive": True
            }]
        }
        
        # Use the environment variables for API connection
        api_host = os.environ.get('API_HOST', 'host.docker.internal')
        api_port = os.environ.get('API_PORT', '81')
        api_url = f'http://{api_host}:{api_port}/api/artists'
        
        app.logger.info(f"Attempting to connect to: {api_url}")
        app.logger.info(f"Sending data: {artist_data}")
        
        response = requests.post(api_url, json=artist_data, timeout=10)
        response.raise_for_status()
        
        return jsonify(response.json()), 201
    except requests.RequestException as e:
        app.logger.error(f"Error creating artist: {str(e)}")
        return jsonify({'error': f"Error creating artist: {str(e)}"}), 500
    except Exception as e:
        app.logger.error(f"An error occurred: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

def get_latest_mp3_data():
    # This function reuses the logic from the latest_mp3 endpoint
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
        SELECT id, mp3_file, youtube_url, title, file_path, artist_name, artist_id, 
               album_name, album_id, track_number, genre, year, duration, 
               album_cover_url, artist_thumb_url, lyrics
        FROM mp3_file 
        ORDER BY id DESC 
        LIMIT 1
        """
        cursor.execute(query)
        result = cursor.fetchone()
        
        if result:
            ytmusic_info = get_ytmusic_info(result['title'])
            mp3_info = get_mp3_info(result['file_path'])
            
            for key, value in {**ytmusic_info, **mp3_info}.items():
                if key not in result or result[key] is None:
                    result[key] = value
            
            if 'thumbnails' in ytmusic_info and ytmusic_info['thumbnails']:
                result['album_thumb_url'] = ytmusic_info['thumbnails'][-1]['url']
            
            return result
        else:
            return None
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@api.route('/debug_fs', methods=['GET'])
def debug_fs():
    try:
        debug_info = {
            'cwd': os.getcwd(),
            'listdir_root': os.listdir('/'),
            'listdir_var': os.listdir('/var'),
            'listdir_www': os.listdir('/var/www'),
            'listdir_html': os.listdir('/var/www/html'),
            'listdir_public': os.listdir('/var/www/html/public'),
            'listdir_converted': os.listdir('/var/www/html/public/converted_files'),
            'stat_converted': {
                'mode': stat.filemode(os.stat('/var/www/html/public/converted_files').st_mode),
                'uid': os.stat('/var/www/html/public/converted_files').st_uid,
                'gid': os.stat('/var/www/html/public/converted_files').st_gid,
            }
        }
        return jsonify(debug_info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api.route('/check_files', methods=['GET'])
def check_files():
    try:
        app.logger.info(f"Checking files in: {SHARED_MP3_PATH}")
        if os.path.exists(SHARED_MP3_PATH):
            files = os.listdir(SHARED_MP3_PATH)
            file_info = []
            for file in files:
                file_path = os.path.join(SHARED_MP3_PATH, file)
                stats = os.stat(file_path)
                file_info.append({
                    'name': file,
                    'size': stats.st_size,
                    'size_mb': round(stats.st_size / (1024 * 1024), 2),  # Size in MB
                    'last_modified': datetime.fromtimestamp(stats.st_mtime).isoformat()
                })
            app.logger.info(f"Found {len(files)} files")
        else:
            app.logger.error(f"Directory does not exist: {SHARED_MP3_PATH}")
            file_info = []
        
        return jsonify({
            'files': file_info,
            'count': len(file_info),
            'total_size_mb': round(sum(f['size'] for f in file_info) / (1024 * 1024), 2),
            'debug_info': {
                'cwd': os.getcwd(),
                'cwd_contents': os.listdir('.'),
                'root_contents': os.listdir('/'),
                'shared_path_exists': os.path.exists(SHARED_MP3_PATH),
                'shared_path': SHARED_MP3_PATH
            }
        })
    except Exception as e:
        app.logger.error(f"Error checking files: {str(e)}")
        return jsonify({'error': str(e), 'debug_info': {
            'cwd': os.getcwd(),
            'cwd_contents': os.listdir('.'),
            'root_contents': os.listdir('/'),
            'shared_path_exists': os.path.exists(SHARED_MP3_PATH),
            'shared_path': SHARED_MP3_PATH
        }}), 500

# Add this line at the end of your file, before the if __name__ == '__main__': block
app.register_blueprint(api)

# Swagger UI configuration
SWAGGER_URL = '/swagger'
API_URL = '/swagger.json'  # Our API url (can of course be a local resource)

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "Your API Name"
    }
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# Route to serve the swagger.json file
@app.route('/swagger.json')
def serve_swagger_spec():
    app.logger.info("Serving swagger.json")
    try:
        with open('swagger.yaml', 'r') as f:
            return jsonify(yaml.safe_load(f))
    except Exception as e:
        app.logger.error(f"Error serving swagger.json: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return "Flask app is running. Swagger should be available at /swagger"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
