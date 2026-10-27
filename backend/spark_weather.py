"""Read-only current weather for an explicitly selected city. No device tracking."""
import asyncio
import math
import time
from collections import OrderedDict

import aiohttp


def condition(code):
    if code == 0:
        return 'Clear skies'
    if code in (1, 2):
        return 'Partly cloudy'
    if code == 3:
        return 'Overcast'
    if code in (45, 48):
        return 'Foggy'
    if code in (51, 53, 55, 56, 57):
        return 'Drizzle'
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return 'Rain'
    if code in (71, 73, 75, 77, 85, 86):
        return 'Snow'
    if code in (95, 96, 99):
        return 'Thunderstorms'
    return 'Conditions unavailable'


async def fetch_json(url, params):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
        async with session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.json()


class DashboardWeather:
    def __init__(self, fetch=fetch_json, clock=time.time):
        self.fetch, self.clock = fetch, clock
        self.cache = OrderedDict()
        self.lock = asyncio.Lock()

    async def current(self, city):
        if not isinstance(city, str) or not 2 <= len(city.strip()) <= 80 or any(ord(c) < 32 for c in city):
            return {'ok': False, 'message': 'Enter a city name between 2 and 80 characters.'}
        city = city.strip()
        key = city.casefold()
        async with self.lock:
            saved = self.cache.get(key)
            if saved and self.clock() - saved[0] < 600:
                self.cache.move_to_end(key)
                return dict(saved[1])
            try:
                places = await self.fetch('https://geocoding-api.open-meteo.com/v1/search',
                                          {'name': city, 'count': 1, 'language': 'en', 'format': 'json'})
                matches = places.get('results', [])
                if not matches:
                    return {'ok': False, 'message': 'City not found. Try the city and country.'}
                place = matches[0]
                raw = await self.fetch('https://api.open-meteo.com/v1/forecast', {
                    'latitude': place['latitude'], 'longitude': place['longitude'],
                    'current': 'temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day',
                    'timezone': 'auto', 'timeformat': 'unixtime', 'forecast_days': 1,
                })
                reading = raw['current']
                numeric = ('temperature_2m', 'apparent_temperature', 'relative_humidity_2m', 'wind_speed_10m', 'time', 'weather_code')
                if any(type(reading.get(k)) not in (int, float) or not math.isfinite(reading[k]) for k in numeric):
                    raise ValueError('Incomplete weather reading')
                if not -900 <= self.clock() - reading['time'] <= 3600:
                    raise ValueError('Outdated weather reading')
                result = {'ok': True, 'city': place['name'], 'region': place.get('admin1', ''),
                          'country': place.get('country', ''), 'timezone': raw['timezone'],
                          'temperature': reading['temperature_2m'], 'feels_like': reading['apparent_temperature'],
                          'humidity': reading['relative_humidity_2m'], 'wind_kmh': reading['wind_speed_10m'],
                          'condition': condition(reading['weather_code']), 'code': reading['weather_code'],
                          'is_day': reading.get('is_day') == 1, 'observed_at': reading['time'],
                          'source': 'Open-Meteo'}
                self.cache[key] = (self.clock(), result)
                while len(self.cache) > 16:
                    self.cache.popitem(last=False)
                return dict(result)
            except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, TypeError, ValueError):
                return {'ok': False, 'message': 'Live weather is unavailable. Please try again shortly.'}
