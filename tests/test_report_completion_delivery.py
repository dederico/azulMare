import unittest

from app.services.report_completion_delivery import (
    bind_report_completion_context,
    build_report_completion_message,
    get_pending_report_completion,
    report_completion_belongs_to_inbound,
    resolve_report_completion_origin,
    stage_report_completion_delivery,
)
from app.services.report_state import _json_safe


class ReportCompletionDeliveryTests(unittest.TestCase):
    def test_model_tool_context_is_bound_to_the_current_inbound(self):
        session = {"report_intent_confirmed": True}

        context = bind_report_completion_context(
            session,
            request_id="request-1",
            origin_uid="inbound-1",
            origin_message_id="message-1",
            client_id="client-1",
            channel_id="channel-1",
            transport="wa_direct",
        )

        self.assertEqual(session["completion_delivery_context"], context)
        self.assertEqual(context["origin_uid"], "inbound-1")
        self.assertEqual(context["origin_message_id"], "message-1")

    def test_legacy_completion_without_origin_never_claims_current_inbound(self):
        completion = {
            "folio": "475912",
            "request_id": "report-request-1",
            "origin_uid": None,
            "origin_message_id": None,
        }

        origin_uid, origin_message_id = resolve_report_completion_origin(
            completion
        )

        self.assertEqual(origin_uid, "completion-outbox:report-request-1")
        self.assertEqual(origin_message_id, "completion-outbox:report-request-1")
        self.assertNotEqual(origin_uid, "new-report-inbound")

    def test_completion_preserves_its_recorded_origin(self):
        origin_uid, origin_message_id = resolve_report_completion_origin(
            {
                "folio": "475912",
                "origin_uid": "inbound-1",
                "origin_message_id": "message-1",
            }
        )

        self.assertEqual((origin_uid, origin_message_id), ("inbound-1", "message-1"))

    def test_only_the_creating_inbound_owns_a_model_tool_completion(self):
        completion = {
            "folio": "475912",
            "notification_message": "Folio 475912 confirmado.",
            "origin_uid": "inbound-1",
            "origin_message_id": "message-1",
            "notified_at": None,
        }

        self.assertTrue(
            report_completion_belongs_to_inbound(completion, "inbound-1")
        )
        self.assertFalse(
            report_completion_belongs_to_inbound(completion, "inbound-2")
        )
        self.assertFalse(
            report_completion_belongs_to_inbound(
                {**completion, "origin_uid": None},
                "inbound-2",
            )
        )

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
