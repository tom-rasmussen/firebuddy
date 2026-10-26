"""Live Phase-1 check: prints real fires, NWS alerts, wind, and shelters for a
Danville, CA address. Run with: python scripts/verify_phase1.py
"""

from firebuddy.sources import fires, geocode, nws, shelters

ADDRESS = "3301 Camino Tassajara, Danville, CA"


def main():
    loc = geocode.geocode(ADDRESS)
    print(f"Geocoded: {loc['matched_address']} ({loc['lat']}, {loc['lon']}) via {loc['source']}")
    lat, lon = loc["lat"], loc["lon"]

    print("\nFires within 50 mi:")
    for f in fires.fires_near(lat, lon, 50):
        print(f"  {f['name']}: {f['acres']} ac, {f['percent_contained']}% contained, "
              f"{f['distance_mi']} mi {f['direction']}")
    if not fires.fires_near(lat, lon, 50):
        print("  none")

    print("\nActive NWS alerts:")
    alerts = nws.official_alerts(lat, lon)
    for a in alerts:
        print(f"  {a['event']}: {a['headline']}")
    if not alerts:
        print("  none")

    print("\nWind:")
    w = nws.wind_data(lat, lon)
    print(f"  station {w['station_id']} ({w['station_distance_mi']} mi away), obs at {w['obs_time']}")
    print(f"  from {w['wind_from_deg']} deg at {w['wind_speed_mph']} mph, gust {w['wind_gust_mph']} mph")
    print(f"  next hours: {w['forecast_hourly'][:3]}")

    print("\nOpen shelters within 50 mi:")
    sh = shelters.find_shelters(lat, lon, max_results=3)
    for s in sh:
        print(f"  {s['name']}, {s['address']} ({s['distance_mi']} mi)")
    if not sh:
        print("  none")


if __name__ == "__main__":
    main()
