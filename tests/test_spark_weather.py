import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_weather import DashboardWeather, condition


class WeatherTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 1793030500
        self.calls = []
        self.reading = {'time': self.now - 100, 'temperature_2m': 24.4,
                        'apparent_temperature': 28.9, 'relative_humidity_2m': 86,
                        'wind_speed_10m': 2.1, 'weather_code': 3, 'is_day': 0}

        async def fetch(url, params):
            self.calls.append((url, params))
            if 'geocoding' in url:
                return {'results': [{'name': 'Coimbatore', 'latitude': 11.0,
                                     'longitude': 76.96, 'country': 'India'}]}
            return {'timezone': 'Asia/Kolkata', 'current': self.reading}

        self.service = DashboardWeather(fetch=fetch, clock=lambda: self.now)

    async def test_live_reading_preserves_observation_time_and_caches_city(self):
        result = await self.service.current('Coimbatore')
        self.assertTrue(result['ok'])
        self.assertEqual((result['city'], result['temperature'], result['condition']),
                         ('Coimbatore', 24.4, 'Overcast'))
        self.assertEqual(result['observed_at'], self.now - 100)
        await self.service.current(' COIMBATORE ')
        self.assertEqual(len(self.calls), 2)
        self.now += 601
        await self.service.current('Coimbatore')
        self.assertEqual(len(self.calls), 4)

    async def test_stale_or_invalid_readings_are_never_presented_as_current(self):
        for change in ({'time': self.now - 7200}, {'temperature_2m': float('nan')},
                       {'temperature_2m': None}, {'time': self.now + 7200}):
            original = dict(self.reading)
            self.reading.update(change)
            self.assertFalse((await self.service.current('Coimbatore'))['ok'])
            self.reading = original
        self.assertEqual(len(self.service.cache), 0)

    async def test_no_city_or_arbitrary_url_is_requested_for_invalid_input(self):
        for city in (None, {}, '', 'a', 'x' * 81, 'city\nname'):
            self.assertFalse((await self.service.current(city))['ok'])
        self.assertEqual(self.calls, [])

    async def test_timeout_and_unknown_city_have_useful_empty_states(self):
        async def timeout(*args):
            raise asyncio.TimeoutError()
        self.service.fetch = timeout
        self.assertIn('unavailable', (await self.service.current('Coimbatore'))['message'])
        async def empty(*args):
            return {'results': []}
        self.service.fetch = empty
        self.assertIn('not found', (await self.service.current('Unknown'))['message'])

    def test_severe_weather_is_not_labelled_clear(self):
        self.assertEqual(condition(95), 'Thunderstorms')
        self.assertEqual(condition(65), 'Rain')
        self.assertEqual(condition(999), 'Conditions unavailable')


if __name__ == '__main__':
    unittest.main()
