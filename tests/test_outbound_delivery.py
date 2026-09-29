import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.services.outbound_delivery import post_json_with_retry


def async_client_factory(post):
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = post
    return MagicMock(return_value=client)


class OutboundDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_transient_network_failure_without_losing_response(self):
        success = MagicMock(status_code=200)
        post = AsyncMock(
            side_effect=[httpx.ConnectTimeout("temporal"), success]
        )

        with patch("asyncio.sleep", new=AsyncMock()) as sleep:
            result = await post_json_with_retry(
                "https://example.test/messages",
                json={"text": "respuesta"},
                headers={"Authorization": "token"},
                client_factory=async_client_factory(post),
            )

        self.assertIs(result, success)
        self.assertEqual(post.await_count, 2)
        sleep.assert_awaited_once()

    async def test_does_not_retry_http_status_because_post_may_be_accepted(self):
        unavailable = MagicMock(status_code=503)
        success = MagicMock(status_code=200)
        post = AsyncMock(side_effect=[unavailable, success])

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await post_json_with_retry(
                "https://example.test/messages",
                json={"text": "respuesta"},
                headers={},
                client_factory=async_client_factory(post),
            )

        self.assertIs(result, unavailable)
        self.assertEqual(post.await_count, 1)

    async def test_does_not_retry_read_timeout_with_ambiguous_delivery(self):
        post = AsyncMock(side_effect=httpx.ReadTimeout("respuesta tardía"))

        with self.assertRaises(httpx.ReadTimeout):
            await post_json_with_retry(
                "https://example.test/messages",
                json={"text": "respuesta"},
                headers={},
                client_factory=async_client_factory(post),
            )

        self.assertEqual(post.await_count, 1)

    async def test_does_not_retry_permanent_client_error(self):
        bad_request = MagicMock(status_code=400)
        post = AsyncMock(return_value=bad_request)

        result = await post_json_with_retry(
            "https://example.test/messages",
            json={"text": "respuesta"},
            headers={},
            client_factory=async_client_factory(post),
        )

        self.assertIs(result, bad_request)
        self.assertEqual(post.await_count, 1)

    async def test_raises_after_last_network_attempt_for_durable_retry(self):
        post = AsyncMock(side_effect=httpx.ConnectTimeout("sin conexión"))

        with patch("asyncio.sleep", new=AsyncMock()):
            with self.assertRaises(httpx.ConnectTimeout):
                await post_json_with_retry(
                    "https://example.test/messages",
                    json={"text": "respuesta"},
                    headers={},
                    client_factory=async_client_factory(post),
                )

        self.assertEqual(post.await_count, 3)


if __name__ == "__main__":
    unittest.main()
