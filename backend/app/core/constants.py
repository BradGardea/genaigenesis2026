"""Application-wide URL constants for external data providers."""

# USGS Earthquake feed (hourly, all magnitudes)
USGS_FEED = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"

# NOAA / NWS active weather alerts
NOAA_ALERTS_URL = "https://api.weather.gov/alerts/active"

# GDACS global disaster event list
GDACS_EVENTS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"

# Open-Meteo free weather forecast API (no key required)
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# NHC current tropical storm advisory JSON
NHC_ACTIVE_STORMS_URL = "https://www.nhc.noaa.gov/CurrentStorms.json"

# USGS Water Services instantaneous values endpoint
NOAA_WATER_SERVICES_URL = "https://waterservices.usgs.gov/nwis/iv/"
