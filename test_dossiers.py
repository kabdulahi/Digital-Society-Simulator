import unittest

from simulator import Settings, Society


class DossierTests(unittest.TestCase):
    def test_internal_and_external_membership(self):
        society = Society(Settings())
        society.step()
        for org_id in range(len(society.organizations)):
            entries = society.dossier_entries(org_id, 1, 0)
            self.assertTrue(any(entry.kind == "Terugkoppeling" for entry in entries))
            self.assertTrue(any(entry.kind == "Organisatiebericht" for entry in entries))
            for entry in entries:
                if entry.kind not in ("Intern gesprek", "Extern gesprek"):
                    continue
                sender = society.individuals[int(entry.sender[1:])].affiliation
                recipient = society.individuals[int(entry.recipient[1:])].affiliation
                self.assertIn(org_id, (sender, recipient))
                self.assertEqual(entry.kind == "Intern gesprek", sender == recipient)
                self.assertIn("gegenereerd", entry.evidence)

    def test_chronology_filters_and_episode_boundary(self):
        society = Society(Settings())
        society.step()
        before = society.dossier_entries(0, 1, 0)
        society.new_episode()
        society._dossier_entry(0, "Terugkoppeling", "leden", "organisatie", "test", "nieuw", "bewijs")
        self.assertEqual(society.dossier_entries(0, 1, 0), before)
        self.assertEqual(society.dossier_entries(0, 1, 1)[-1].message, "nieuw")
        self.assertEqual(len(society.dossier_entries(0, 1, 1, query="BEWIJS")), 1)
        self.assertTrue(all(e.kind == "Intern gesprek" for e in society.dossier_entries(0, 1, 1, kind="Intern gesprek")))

    def test_retention_is_bounded_and_reported(self):
        society = Society(Settings())
        for _ in range(5001):
            society._dossier_entry(0, "test", "a", "b", "c", "d", "e")
        self.assertEqual(len(society.dossiers[0]), 5000)
        self.assertEqual(society.dossier_discarded[0], 1)


if __name__ == "__main__":
    unittest.main()
