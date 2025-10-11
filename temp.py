import requests
import psycopg2
import sys
DB_URL = "postgresql://postgres.fqxuzxqrvzdncsjlvkqk:wg7fCt8RYM9hjDAR@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres"


try:
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    print("✅ Connected to Supabase Postgres database.")
except Exception as e:
    print("❌ Database connection failed:", e)
    sys.exit(1)

sql = "SELECT address FROM users WHERE user_id = %s"
cursor.execute(sql, (8,))
result = cursor.fetchone()
query = "Batangas College of Arts and Sciences, Lipa City, Batangas, Philippines"
url = f"https://photon.komoot.io/api/?q={result}"
response = requests.get(url).json()

if response["features"]:
    coords = response["features"][0]["geometry"]["coordinates"]
    print(f"Longitude: {coords[0]}, Latitude: {coords[1]}")
    sql = "UPDATE users SET longitude = %s, latitude = %s WHERE user_id = %s"
    cursor.execute(sql, (coords[0], coords[1], 8))
else:
    print("Address not found.")