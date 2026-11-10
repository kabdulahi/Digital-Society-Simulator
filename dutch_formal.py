"""A small lexicalized, feature-aware Dutch clause recognizer and generator.

Rejection means outside this fragment, not necessarily ungrammatical Dutch.
"""
import json
import random
import re
from pathlib import Path


class FragmentError(ValueError):
    pass


class DutchFragment:
    def __init__(self, path=None):
        path = path or Path(__file__).with_name("language") / "formele_grammatica.json"
        with open(path, encoding="utf-8") as stream:
            self.data = json.load(stream)
        self.subjects = dict(self.data["subjects"])
        objects = set(self.data["objects"])
        self.relative_pronouns = {phrase: ("dat" if phrase.startswith("het ") else "die")
                                  for phrase in self.subjects if phrase.startswith(("de ", "het "))}
        for noun in self.data.get("nouns", []):
            article = "het" if noun["gender"] == "neuter" else "de"
            def add(phrase, agreement, relative):
                self.subjects[phrase] = agreement
                self.relative_pronouns[phrase] = relative
                objects.add(phrase)
            add(f"{article} {noun['singular']}", "3sg", "dat" if article == "het" else "die")
            add(f"een {noun['singular']}", "3sg", "dat" if article == "het" else "die")
            add(f"de {noun['plural']}", "pl", "die")
            for adjective in self.data.get("adjectives", []):
                inflected = adjective["inflected"]
                bare = adjective["base"] if article == "het" else inflected
                add(f"{article} {inflected} {noun['singular']}", "3sg", "dat" if article == "het" else "die")
                add(f"een {bare} {noun['singular']}", "3sg", "dat" if article == "het" else "die")
                add(f"de {inflected} {noun['plural']}", "pl", "die")
        self.objects = sorted(objects)
        self.subject_phrases = sorted(self.subjects, key=lambda x: len(x.split()), reverse=True)
        self.object_phrases = sorted(self.objects, key=lambda x: len(x.split()), reverse=True)
        self.verbs = self.data["verbs"]
        self.adverbs = self.data["adverbs"]
        self.complementizers = self.data["complementizers"]

    def _subject(self, tokens, position):
        for phrase in self.subject_phrases:
            words = phrase.split()
            if tokens[position:position + len(words)] == words:
                return phrase, self.subjects[phrase], position + len(words)
        raise FragmentError("Onderwerp niet herkend in het lexicon")

    def _verb(self, word, agreement, inverted=False):
        index = {"1sg": 0, "2sg": 1, "3sg": 2, "pl": 3}[agreement]
        for verb in self.verbs:
            expected = verb["inverted"] if inverted and agreement == "2sg" else verb["forms"][index]
            if word == expected:
                return verb
        raise FragmentError("Werkwoord onbekend of geen overeenkomst met het onderwerp")

    def _object(self, tokens, position):
        for phrase in self.object_phrases:
            words = phrase.split()
            if tokens[position:position + len(words)] == words:
                return phrase, position + len(words)
        raise FragmentError("Object niet herkend in het lexicon")

    def _relative(self, tokens, position, subject, agreement):
        if position >= len(tokens) or tokens[position] not in ("die", "dat"):
            return None, position
        relative = tokens[position]
        if self.relative_pronouns.get(subject) != relative:
            raise FragmentError("Betrekkelijk voornaamwoord past niet bij het antecedent")
        position += 1
        try:
            obj, after = self._object(tokens, position)
            if after < len(tokens):
                verb = self._verb(tokens[after], agreement)
                if verb["frame"] == "transitive":
                    return {"category": "relatieve bijzin", "pronoun": relative,
                            "object": obj, "verb": verb["lemma"], "order": "verb-final"}, after + 1
        except FragmentError:
            pass
        if position >= len(tokens): raise FragmentError("Persoonsvorm ontbreekt in de relatieve bijzin")
        verb = self._verb(tokens[position], agreement)
        if verb["frame"] != "intransitive":
            raise FragmentError("Onvolledige relatieve bijzin")
        return {"category": "relatieve bijzin", "pronoun": relative,
                "verb": verb["lemma"], "order": "verb-final"}, position + 1

    def _clause(self, tokens, position=0, subordinate=False, inverted=False, depth=0):
        if depth > 8:
            raise FragmentError("Maximale recursiediepte (8) bereikt")
        complementizer = None
        if subordinate:
            if position >= len(tokens) or tokens[position] not in self.complementizers:
                raise FragmentError("Bijzin heeft een voegwoord nodig")
            complementizer = tokens[position]; position += 1
        if inverted:
            if position >= len(tokens): raise FragmentError("Persoonsvorm ontbreekt")
            form = tokens[position]; position += 1
            subject, agreement, position = self._subject(tokens, position)
            relative, position = self._relative(tokens, position, subject, agreement)
            verb = self._verb(form, agreement, True)
        else:
            subject, agreement, position = self._subject(tokens, position)
            relative, position = self._relative(tokens, position, subject, agreement)
            if position >= len(tokens): raise FragmentError("Persoonsvorm ontbreekt")
            # A verb-final subordinate can contain an object before its finite verb.
            if subordinate:
                try:
                    obj, after = self._object(tokens, position)
                    if after < len(tokens):
                        verb = self._verb(tokens[after], agreement)
                        if verb["frame"] == "transitive":
                            node = {"category": "CP", "complementizer": complementizer,
                                    "subject": subject, "agreement": agreement, "object": obj,
                                    "verb": verb["lemma"], "order": "verb-final"}
                            if relative: node["relative"] = relative
                            return node, after + 1
                except FragmentError:
                    pass
            verb = self._verb(tokens[position], agreement); position += 1
        node = {"category": "CP" if subordinate else "S", "subject": subject,
                "agreement": agreement, "verb": verb["lemma"],
                "order": "verb-final" if subordinate else ("V1/inversion" if inverted else "V2")}
        if complementizer: node["complementizer"] = complementizer
        if relative: node["relative"] = relative
        if verb["frame"] == "transitive":
            if subordinate: raise FragmentError("Object moet vóór de persoonsvorm in deze bijzin")
            node["object"], position = self._object(tokens, position)
        elif verb["frame"] == "clausal":
            if position >= len(tokens) or tokens[position] != "dat":
                raise FragmentError("Dit werkwoord vereist een dat-bijzin")
            node["complement"], position = self._clause(tokens, position, subordinate=True, depth=depth+1)
        return node, position

    def parse(self, text):
        text = text.strip().casefold()
        if not text: raise FragmentError("Voer een zin in")
        tokens = re.findall(r"[^\W\d_]+|[^\s\w]", text, flags=re.UNICODE)
        if tokens and tokens[-1] in (".", "?"): punctuation = tokens.pop()
        else: punctuation = ""
        if not tokens or any(not t.isalpha() for t in tokens):
            raise FragmentError("Alleen woorden en een afsluitend punt of vraagteken worden ondersteund")
        if tokens[0] in self.complementizers:
            node, end = self._clause(tokens, subordinate=True)
        elif tokens[0] in self.adverbs:
            node, end = self._clause(tokens, 1, inverted=True)
            node["fronted"] = tokens[0]; node["order"] = "V2/inversion"
        else:
            node, end = self._clause(tokens, inverted=punctuation == "?")
        if end != len(tokens): raise FragmentError("Niet-verwerkte woorden of woordvolgorde buiten dit fragment")
        return node

    def generate(self, seed):
        rng = random.Random(seed)
        subject = rng.choice(list(self.subjects))
        agreement = self.subjects[subject]
        verb = rng.choice([v for v in self.verbs if v["frame"] == "transitive"])
        form = verb["forms"][{"1sg": 0, "2sg": 1, "3sg": 2, "pl": 3}[agreement]]
        result = f"{subject.capitalize()} {form} {rng.choice(self.objects)}."
        return result
