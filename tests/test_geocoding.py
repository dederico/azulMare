import unittest
from types import SimpleNamespace
from unittest.mock import patch

from geopy.exc import GeocoderTimedOut

from app.services.functions.implementations.geocoding import (
    reverse_geocode_location,
)


class ReverseGeocodingTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.functions.implementations.geocoding.Nominatim")
    async def test_returns_structured_components_for_report_fields(self, nominatim):
        nominatim.return_value.reverse.return_value = SimpleNamespace(
            address="Río Balsas 303, Del Valle, San Pedro Garza García",
            raw={
                "address": {
                    "road": "Río Balsas",
                    "house_number": "303",
                    "suburb": "Del Valle",
                    "city": "San Pedro Garza García",
                }
            },
        )

        result = await reverse_geocode_location(25.65, -100.37)

        self.assertTrue(result["success"])
        self.assertEqual(result["street"], "Río Balsas")
        self.assertEqual(result["number"], "303")
        self.assertEqual(result["colony"], "Del Valle")
        self.assertIn("San Pedro Garza García", result["formatted_address"])
        nominatim.return_value.reverse.assert_called_once()

    @patch("app.services.functions.implementations.geocoding.Nominatim")
    async def test_geocoder_failure_returns_no_address_data(self, nominatim):
        nominatim.return_value.reverse.side_effect = GeocoderTimedOut("timeout")

        result = await reverse_geocode_location(25.65, -100.37)

        self.assertFalse(result["success"])
        self.assertEqual(result["street"], "")
        self.assertEqual(result["number"], "")
        self.assertEqual(result["colony"], "")


if __name__ == "__main__":
    unittest.main()
