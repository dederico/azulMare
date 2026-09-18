import unittest
from unittest.mock import patch

import app.services.evaluation_state as evaluation_state_module
from app.services.evaluation_state import (
    clear_evaluation_state,
    get_evaluation_state,
    save_evaluation_state,
)


class EvaluationStateTests(unittest.TestCase):
    def setUp(self):
        self.phone = "5218110000099"
        clear_evaluation_state(None, self.phone)

    def tearDown(self):
        clear_evaluation_state(None, self.phone)

    def test_state_survives_outside_the_request_session(self):
        save_evaluation_state(
            None,
            self.phone,
            state="evaluacion_esperando_motivo",
            folio="472988",
            client_id=123,
            channel_id=43906,
            now=1000,
        )

        state = get_evaluation_state(None, self.phone, now=1001)

        self.assertEqual(state["state"], "evaluacion_esperando_motivo")
        self.assertEqual(state["folio"], "472988")
        self.assertEqual(state["client_id"], 123)
        self.assertEqual(state["channel_id"], 43906)

    def test_completed_state_is_removed(self):
        save_evaluation_state(
            None,
            self.phone,
            state="evaluacion_esperando_motivo",
            folio="472988",
        )

        self.assertTrue(clear_evaluation_state(None, self.phone))
        self.assertIsNone(get_evaluation_state(None, self.phone))

    def test_stale_state_is_not_restored(self):
        save_evaluation_state(
            None,
            self.phone,
            state="evaluacion_esperando_motivo",
            folio="472988",
            now=1000,
        )

        self.assertIsNone(
            get_evaluation_state(
                None,
                self.phone,
                max_age_seconds=60,
                now=1061,
            )
        )

    def test_database_absence_does_not_revive_stale_process_memory(self):
        save_evaluation_state(
            None,
            self.phone,
            state="evaluacion_esperando_motivo",
            folio="472988",
        )

        class EmptyCursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, *_args, **_kwargs):
                return None

            def fetchone(self):
                return None

        class EmptyConnection:
            def cursor(self):
                return EmptyCursor()

            def close(self):
                return None

        with (
            patch.object(
                evaluation_state_module,
                "ensure_evaluation_state_storage",
                return_value=True,
            ),
            patch.object(
                evaluation_state_module,
                "_connect",
                return_value=EmptyConnection(),
            ),
        ):
            self.assertIsNone(get_evaluation_state(object(), self.phone))

        self.assertIsNone(get_evaluation_state(None, self.phone))


if __name__ == "__main__":
    unittest.main()
