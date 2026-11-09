import json
import unittest
from pathlib import Path

from simulator import DutchGrammar, Settings, Society


class CommunicationLanguageTests(unittest.TestCase):
    def test_variety_for_the_same_pair_and_state(self):
        messages = {DutchGrammar.sentence("ik", 0.2, 0.4, 0.7, 3, step=step,
                                         sender=0, recipient_opinion=-0.2)
                    for step in range(5500)}
        self.assertGreaterEqual(len(messages), 5000)

    def test_reproducible_and_sensitive_to_actual_opinion_gap(self):
        args = ("ik", 0.2, 0.4, 0.7, 3)
        same = DutchGrammar.sentence(*args, step=4, sender=0, recipient_opinion=0.2)
        different = DutchGrammar.sentence(*args, step=4, sender=0, recipient_opinion=-0.8)
        self.assertEqual(same, DutchGrammar.sentence(*args, step=4, sender=0, recipient_opinion=0.2))
        self.assertNotEqual(same, different)
        data = DutchGrammar._communication
        self.assertTrue(any(text in same for text in data["followup_agree"]))
        self.assertTrue(any(text in different for text in data["followup_disagree"]))

    def test_simulator_logs_generated_text_and_preserves_reproducibility(self):
        first, second = Society(Settings()), Society(Settings())
        for _ in range(3):
            first.step()
            second.step()
        self.assertEqual(first.communication_log, second.communication_log)
        self.assertEqual(first.history, second.history)
        entry = next(e for e in first.dossiers[0] if e.kind in ("Intern gesprek", "Extern gesprek"))
        self.assertIn("gegenereerd", entry.evidence)
        self.assertGreater(len(entry.message.split()), 15)

    def test_data_and_analysis_are_honest_about_scope(self):
        data = json.loads((Path(__file__).parent / "language" / "communicatie.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["topics"]), 40)
        result = DutchGrammar.analyze("Dit is niet grammaticaal beoordeeld.")
        self.assertIsNone(result["syntax"]["accepted_fragment"])
        self.assertEqual(result["semantics"]["roles"], [])
        self.assertEqual(result["semantics"]["domains"], [])


if __name__ == "__main__":
    unittest.main()
