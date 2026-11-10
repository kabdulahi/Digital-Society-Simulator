import unittest
from dataclasses import FrozenInstanceError

from dutch_formal import DutchFragment, FragmentError
from formal_models import Physiology, physiology_step, synthetic_assessment, effective_sample_size, nested_belief_proxy
from simulator import Society, Settings


class DutchFragmentTests(unittest.TestCase):
    def setUp(self): self.grammar = DutchFragment()

    def test_v2_inversion_question_and_verb_final(self):
        cases = {"De student leest het boek.": "V2",
                 "Vandaag leest de student het boek.": "V2/inversion",
                 "Leest de student het boek?": "V1/inversion",
                 "dat de student het boek leest.": "verb-final",
                 "Werk jij?": "V1/inversion",
                 "De kinderen werken.": "V2"}
        for sentence, order in cases.items():
            with self.subTest(sentence=sentence): self.assertEqual(self.grammar.parse(sentence)["order"], order)

    def test_agreement_valency_and_order_rejected(self):
        for sentence in ("De kinderen werkt.", "De student lees het boek.",
                         "dat de student leest het boek.", "De student leest.", "Werkt jij?"):
            with self.subTest(sentence=sentence), self.assertRaises(FragmentError):
                self.grammar.parse(sentence)

    def test_recursion_and_generated_sentences(self):
        tree = self.grammar.parse("Ik denk dat jij denkt dat hij werkt.")
        self.assertEqual(tree["complement"]["complement"]["verb"], "werken")
        for seed in range(500):
            self.grammar.parse(self.grammar.generate(seed))

    def test_determiners_adjectives_and_relative_clauses(self):
        valid = ("Een mooi huis werkt.", "Het mooie huis werkt.",
                 "De student die het boek leest werkt.",
                 "De kinderen die het boek lezen werken.", "Het huis dat werkt werkt.")
        invalid = ("Een mooie huis werkt.", "Het mooi huis werkt.",
                   "De student dat werkt werkt.", "Het huis die werkt werkt.",
                   "De kinderen die het boek leest werken.")
        for sentence in valid:
            with self.subTest(sentence=sentence): self.grammar.parse(sentence)
        for sentence in invalid:
            with self.subTest(sentence=sentence), self.assertRaises(FragmentError): self.grammar.parse(sentence)
        relative = self.grammar.parse(valid[2])["relative"]
        self.assertEqual(relative["object"], "het boek")
        self.assertEqual(relative["verb"], "lezen")

    def test_expanded_lexicon_is_used_by_generator(self):
        self.assertGreaterEqual(len(self.grammar.subjects), 700)
        self.assertGreaterEqual(len(self.grammar.objects), 700)
        for seed in range(100): self.grammar.parse(self.grammar.generate(seed))


class FormalModelTests(unittest.TestCase):
    def test_physiology_bounds_and_parameter_effect(self):
        low = Physiology(reactivity=0.0)
        high = Physiology(reactivity=1.0)
        self.assertGreater(physiology_step(high, 1, 0, 0).activation,
                           physiology_step(low, 1, 0, 0).activation)
        for _ in range(500):
            high = physiology_step(high, 1, 1, 1)
        self.assertTrue(all(0 <= x <= 1 for x in (high.activation, high.fatigue, high.recovery)))

    def test_snapshot_preserves_profile_and_life_course(self):
        society = Society(Settings())
        initial = society.snapshots[0][2][0]
        society.individuals[0].physiology.reactivity = 0.99
        society.step()
        current = society.snapshots[-1][2][0]
        self.assertNotEqual(initial.physiology.reactivity, current.physiology.reactivity)
        self.assertAlmostEqual(current.life_course.age_years - initial.life_course.age_years, 1 / 365.25)

    def test_explicit_formulas(self):
        self.assertEqual(effective_sample_size(5, .75), 1.25)
        self.assertAlmostEqual(nested_belief_proxy(1, -1, 2), .5)
        with self.assertRaises(ValueError): effective_sample_size(0, .5)

    def test_synthetic_observation_uncertainty(self):
        society = Society(Settings())
        person = society.individuals[0]
        person.stress = 0.5
        person.physiology.activation = 0.5
        person.physiology.fatigue = 0.5
        person.physiology.observation_uncertainty = 0.2
        uncertain = synthetic_assessment(person, 1, 0)
        self.assertEqual(uncertain.category, "onzeker")
        self.assertAlmostEqual(uncertain.observed, .5)
        self.assertAlmostEqual(uncertain.lower, .3)
        self.assertAlmostEqual(uncertain.upper, .7)
        person.physiology.observation_uncertainty = 0
        self.assertEqual(synthetic_assessment(person, 1, 0).category, "midden")
        with self.assertRaises(FrozenInstanceError):
            uncertain.category = "hoog"

    def test_assessment_is_reproducible_and_snapshot_isolated(self):
        a, b = Society(Settings()), Society(Settings())
        for _ in range(3): a.step(); b.step()
        self.assertEqual(a.individuals[0].assessment, b.individuals[0].assessment)
        prior = a.snapshots[-1][2][0].assessment
        a.individuals[0].stress = 1.0
        a._update_assessment(a.individuals[0])
        self.assertEqual(a.snapshots[-1][2][0].assessment, prior)
        self.assertNotEqual(a.individuals[0].assessment, prior)

    def test_category_change_appears_in_organization_dossier(self):
        society = Society(Settings())
        person = society.individuals[0]
        person.physiology.observation_uncertainty = 0
        person.stress = 0
        person.physiology.activation = 0
        person.physiology.fatigue = 0
        society._update_assessment(person, record=False)
        person.stress = 1
        person.physiology.activation = 1
        person.physiology.fatigue = 1
        society._update_assessment(person)
        events = society.dossier_entries(person.affiliation, 0, 0, kind="Modelinschatting", member="P00")
        self.assertEqual(len(events), 1)
        self.assertIn("laag → hoog", events[0].message)
        self.assertIn("geen echte meting", events[0].evidence)


if __name__ == "__main__": unittest.main()
