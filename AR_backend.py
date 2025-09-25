from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import requests
import json
import sqlite3
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configuration
MAPBOX_ACCESS_TOKEN = 'YOUR_MAPBOX_ACCESS_TOKEN'
MAPBOX_DIRECTIONS_URL = 'https://api.mapbox.com/directions/v5/mapbox/walking'

# Initialize database
def init_db():
    conn = sqlite3.connect('pathvision.db')
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pois (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT, 
            latitude REAL,
            longitude REAL,
            description TEXT,
            indoor_map TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS navigation_logs (
            id INTEGER PRIMARY KEY,
            user_id TEXT,
            start_location TEXT,
            end_location TEXT,
            timestamp DATETIME,
            route_data TEXT
        )
    ''')
    
    # Insert sample POIs
    sample_pois = [
        ('Main Entrance', 'entrance', 18.5204, 73.8567, 'Primary building entrance', 'floor_1_map.json'),
        ('Cafeteria', 'dining', 18.5210, 73.8575, 'Student dining area', 'floor_2_map.json'),
        ('Library', 'education', 18.5215, 73.8580, 'Central library', 'floor_3_map.json'),
        ('Restroom', 'facilities', 18.5200, 73.8560, 'Public restroom facilities', 'floor_1_map.json'),
        ('Information Desk', 'service', 18.5208, 73.8570, 'Help and information', 'floor_1_map.json'),
        ('Parking Area', 'parking', 18.5195, 73.8550, 'Vehicle parking zone', 'ground_map.json'),
        ('Emergency Exit', 'safety', 18.5212, 73.8565, 'Emergency evacuation route', 'floor_1_map.json'),
        ('Conference Hall', 'meeting', 18.5218, 73.8585, 'Large meeting space', 'floor_2_map.json')
    ]
    
    cursor.executemany('''
        INSERT OR REPLACE INTO pois (name, category, latitude, longitude, description, indoor_map)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', sample_pois)
    
    conn.commit()
    conn.close()

# API Routes
@app.route('/api/pois', methods=['GET'])
def get_pois():
    """Get all Points of Interest"""
    category = request.args.get('category', '')
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    radius = request.args.get('radius', 1000, type=int)  # meters
    
    conn = sqlite3.connect('pathvision.db')
    cursor = conn.cursor()
    
    query = 'SELECT * FROM pois'
    params = []
    
    if category:
        query += ' WHERE category = ?'
        params.append(category)
    
    cursor.execute(query, params)
    pois = cursor.fetchall()
    conn.close()
    
    poi_list = []
    for poi in pois:
        poi_data = {
            'id': poi[0],
            'name': poi[1],
            'category': poi[2],
            'latitude': poi[3],
            'longitude': poi[4],
            'description': poi[5],
            'indoor_map': poi[6]
        }
        
        # Calculate distance if user location provided
        if lat and lon:
            poi_data['distance'] = calculate_distance(lat, lon, poi[3], poi[4])
        
        poi_list.append(poi_data)
    
    return jsonify({'pois': poi_list})

@app.route('/api/route', methods=['POST'])
def get_route():
    """Calculate route between two points"""
    data = request.json
    start = data.get('start')  # [longitude, latitude]
    end = data.get('end')      # [longitude, latitude]
    profile = data.get('profile', 'walking')  # walking, driving, cycling
    
    if not start or not end:
        return jsonify({'error': 'Start and end coordinates required'}), 400
    
    # Build Mapbox API request
    coordinates = f"{start[0]},{start[1]};{end[0]},{end[1]}"
    url = f"https://api.mapbox.com/directions/v5/mapbox/{profile}/{coordinates}"
    
    params = {
        'access_token': MAPBOX_ACCESS_TOKEN,
        'geometries': 'geojson',
        'overview': 'full',
        'steps': 'true',
        'voice_instructions': 'true'
    }
    
    try:
        response = requests.get(url, params=params)
        route_data = response.json()
        
        # Log navigation request
        log_navigation(data.get('user_id', 'anonymous'), start, end, route_data)
        
        return jsonify(route_data)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/indoor-route', methods=['POST'])
def get_indoor_route():
    """Get indoor navigation route using Wi-Fi/Bluetooth beacons"""
    data = request.json
    building_id = data.get('building_id')
    start_beacon = data.get('start_beacon')
    end_beacon = data.get('end_beacon')
    
    # Simulate indoor routing logic
    indoor_directions = [
        {'instruction': 'Head towards the main corridor', 'distance': 10},
        {'instruction': 'Turn right at the information board', 'distance': 15},
        {'instruction': 'Continue straight for 20 meters', 'distance': 20},
        {'instruction': 'Turn left at the end of corridor', 'distance': 8},
        {'instruction': 'Destination reached', 'distance': 0}
    ]
    
    return jsonify({
        'indoor_route': indoor_directions,
        'total_distance': sum(step['distance'] for step in indoor_directions),
        'estimated_time': '2-3 minutes'
    })

@app.route('/api/ar-overlay', methods=['POST'])
def get_ar_overlay():
    """Get AR overlay information for current location"""
    data = request.json
    lat = data.get('latitude')
    lon = data.get('longitude')
    heading = data.get('heading', 0)  # Device compass heading
    
    # Find nearby POIs for AR overlay
    conn = sqlite3.connect('pathvision.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM pois')
    all_pois = cursor.fetchall()
    conn.close()
    
    ar_objects = []
    for poi in all_pois:
        distance = calculate_distance(lat, lon, poi[3], poi[4])
        if distance < 100:  # Within 100 meters
            ar_objects.append({
                'name': poi[1],
                'category': poi[2],
                'distance': round(distance, 1),
                'bearing': calculate_bearing(lat, lon, poi[3], poi[4]),
                'description': poi[5]
            })
    
    return jsonify({'ar_objects': ar_objects})

@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    """Get navigation analytics"""
    conn = sqlite3.connect('pathvision.db')
    cursor = conn.cursor()
    
    # Get popular destinations
    cursor.execute('''
        SELECT end_location, COUNT(*) as count 
        FROM navigation_logs 
        GROUP BY end_location 
        ORDER BY count DESC 
        LIMIT 5
    ''')
    popular_destinations = cursor.fetchall()
    
    # Get usage statistics
    cursor.execute('SELECT COUNT(*) FROM navigation_logs')
    total_navigations = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'total_navigations': total_navigations,
        'popular_destinations': [{'destination': dest[0], 'count': dest[1]} for dest in popular_destinations]
    })

# Utility Functions
def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates in meters"""
    import math
    R = 6371000  # Earth's radius in meters
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_lat/2) * math.sin(delta_lat/2) +
         math.cos(lat1_rad) * math.cos(lat2_rad) *
         math.sin(delta_lon/2) * math.sin(delta_lon/2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

def calculate_bearing(lat1, lon1, lat2, lon2):
    """Calculate bearing between two coordinates"""
    import math
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lon = math.radians(lon2 - lon1)
    
    y = math.sin(delta_lon) * math.cos(lat2_rad)
    x = (math.cos(lat1_rad) * math.sin(lat2_rad) -
         math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon))
    
    bearing = math.atan2(y, x)
    return (math.degrees(bearing) + 360) % 360

def log_navigation(user_id, start, end, route_data):
    """Log navigation request for analytics"""
    conn = sqlite3.connect('pathvision.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO navigation_logs (user_id, start_location, end_location, timestamp, route_data)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, str(start), str(end), datetime.now(), json.dumps(route_data)))
    
    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

if __name__ == '__main__':
    print("Starting PathVisioN AR Navigation Backend...")
    print("Features: AR overlays, indoor positioning, POI management")
    app.run(host='0.0.0.0', port=5000, debug=True)
