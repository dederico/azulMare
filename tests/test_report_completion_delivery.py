import unittest

from app.services.report_completion_delivery import (
    build_report_completion_message,
    get_pending_report_completion,
    stage_report_completion_delivery,
)
from app.services.report_state import _json_safe


class ReportCompletionDeliveryTests(unittest.TestCase):
    def test_completion_without_images_uses_one_canonical_folio_message(self):
        self.assertEqual(
            build_report_completion_message("474570"),
            "Tu reporte ha sido generado con éxito. El número de folio para tu "
            "reporte es 474570. Tu reporte ha sido enviado al sistema. "
            "Agradecemos mucho tu colaboración. Estamos para servirte",
        )

    def test_completion_message_includes_confirmed_folio_and_image_count(self):
        self.assertEqual(
            build_report_completion_message("474580", 1),
            "Tu reporte ha sido generado con éxito. El número de folio para tu "
            "reporte es 474580. Tu reporte con 1 imagen ha sido enviado al "
            "sistema. Agradecemos mucho tu colaboración. Estamos para servirte",
        )

    def test_confirmed_folio_remains_durable_until_notification_delivery(self):
        session = {"report_intent_confirmed": True, "images": ["photo"]}

        pending = stage_report_completion_delivery(
            session,
            folio="474580",
            message="Tu reporte ha sido generado. Folio 474580.",
            request_id="request-1",
            location="Río San Lorenzo 212, Fuentes del Valle",
            image_count=1,
            origin_uid="inbound-1",
            origin_message_id="message-1",
            client_id="client-1",
            channel_id="channel-1",
            transport="wa_direct",
        )
        restored = _json_safe(session)

        self.assertEqual(get_pending_report_completion(restored), pending)
        self.assertEqual(restored["images"], ["photo"])
        self.assertEqual(pending["origin_uid"], "inbound-1")
        self.assertEqual(pending["client_id"], "client-1")

    def test_incomplete_pending_notification_is_not_actionable(self):
        self.assertIsNone(get_pending_report_completion({}))
        self.assertIsNone(
            get_pending_report_completion(
                {"pending_completion_delivery": {"folio": "474580"}}
            )
        )


if __name__ == "__main__":
    unittest.main()
