#!/usr/bin/env python3
"""Digital Society Simulator: synthetic multi-agent cybernetics (stdlib only)."""
from __future__ import annotations
import csv
import copy
import hashlib
import json
import math
import random
import re
import tkinter as tk
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import ttk, filedialog
from formal_models import Physiology, LifeCourse, SyntheticAssessment, physiology_step, observation, synthetic_assessment, group_summary, effective_sample_size, nested_belief_proxy
from dutch_formal import DutchFragment, FragmentError

FORMAL_DUTCH = DutchFragment()

ORG_NAMES = ["Onderwijs", "Gezondheidszorg", "Bestuur", "Media", "Economie", "Onderzoek", "Gemeenschapsraad"]
ORG_COLORS = ["#f59e0b", "#06b6d4", "#a78bfa", "#fb7185", "#34d399", "#60a5fa", "#eab308"]
BG, PANEL, FG, MUTED, ACCENT = "#0b1220", "#111c2d", "#e5eefb", "#9aafc7", "#60a5fa"
LANGUAGE_DIR = Path(__file__).with_name("language")


def _language_data(filename, fallback):
    try:
        with (LANGUAGE_DIR / filename).open(encoding="utf-8") as stream:
            return json.load(stream)
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


class DutchGrammar:
    """C1-georiënteerde, gecontroleerde subset voor betekenisvolle simulatieberichten."""
    _lexicon = _language_data("lexicon.json", {})
    _grammar = _language_data("grammar.json", {})
    _morphology = _language_data("morphology.json", {})
    _semantics = _language_data("semantics.json", {})
    _discourse = _language_data("discourse.json", {})
    _communication = _language_data("communicatie.json", {})
    subjects = _lexicon.get("subjects", ["ik", "jij", "hij", "zij", "wij"])
    verbs = _lexicon.get("verbs", [("analyseren", "analyseert", "analyseren"), ("bespreken", "bespreekt", "bespreken"),
             ("beoordelen", "beoordeelt", "beoordelen"), ("onderzoeken", "onderzoekt", "onderzoeken"),
             ("wegen", "weegt", "wegen"), ("onderbouwen", "onderbouwt", "onderbouwen"),
             ("nuanceren", "nuanceert", "nuanceren"), ("verzoenen", "verzoent", "verzoenen")])
    objects = _lexicon.get("objects", ["de toestand", "het vertrouwen", "de gezamenlijke situatie", "de nieuwe informatie",
               "de institutionele verantwoordelijkheid", "de maatschappelijke consequenties",
               "de onderliggende aannames", "de verdeling van middelen"])
    connectors = _grammar.get("connectors", ["hoewel", "aangezien", "daarentegen", "desondanks", "bijgevolg", "voor zover"])
    adverbs = _lexicon.get("adverbs", ["zorgvuldig", "systematisch", "vooralsnog", "expliciet", "terughoudend", "kritisch"])
    nouns = _lexicon.get("nouns", [])
    evaluations = _lexicon.get("evaluations", [])
    templates = _grammar.get("templates", [])

    @classmethod
    def sentence(cls, subject, opinion, stress, trust, target, *, step=0, sender=0, recipient_opinion=None):
        """Compose controlled Dutch with a local RNG; never consume the simulation RNG."""
        data = cls._communication
        required = ("topics", "subordinate", "responses", "followup_neutral", "followup_agree", "followup_disagree", "transitions", "reflections")
        if not all(data.get(key) for key in required):
            return "Ik wil graag met jou over onze standpunten spreken."
        subject = subject.casefold()
        if subject not in cls.subjects:
            raise ValueError(f"Onbekend onderwerp: {subject}")
        seed = f"{step}|{sender}|{target}|{opinion:.6f}|{stress:.6f}|{trust:.6f}"
        rng = random.Random(int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:8], "big"))
        forms = {
            "ask": ("vraag", "vraagt", "vragen"), "want": ("wil", "wil", "willen"),
            "find": ("vind", "vindt", "vinden"), "think": ("denk", "denkt", "denken"),
            "propose": ("stel", "stelt", "stellen"), "advocate": ("pleit", "pleit", "pleiten"),
            "consider": ("acht", "acht", "achten"), "wish": ("wens", "wenst", "wensen"),
        }
        column = 2 if subject == "wij" else 1 if subject in ("hij", "zij") else 0
        values = {key: variants[column] for key, variants in forms.items()}
        values.update(subject=subject, topic=rng.choice(data["topics"]))
        subordinate = rng.choice(data["subordinate"]).format(**values)
        response = rng.choice(data["responses"]).format(**values)
        if recipient_opinion is None:
            group = "followup_neutral"
        else:
            group = "followup_agree" if abs(opinion - recipient_opinion) < .15 else "followup_disagree"
        followup = rng.choice(data[group])
        reflection = rng.choice(data["reflections"])
        formal_sentence = FORMAL_DUTCH.generate(rng.getrandbits(64))
        return f"{subordinate[0].upper() + subordinate[1:]}, {response}. {followup}. {rng.choice(data['transitions'])} {reflection}. {formal_sentence}"

    @classmethod
    def parse(cls, sentence):
        tokens = re.findall(r"[^\W\d_]+", sentence.lower(), flags=re.UNICODE)
        subordinate = any(w in tokens for w in ("omdat", "dat", "als", "hoewel", "aangezien", "terwijl", "mits"))
        coordination = any(w in tokens for w in ("en", "maar", "of"))
        return {"tokens": len(tokens), "subordinate_clause": subordinate,
                "coordination": coordination, "accepted_fragment": None,
                "method": "oppervlakkige trefwoordherkenning; geen grammaticale validatie"}

    @classmethod
    def analyze(cls, sentence):
        tokens = re.findall(r"[^\W\d_]+", sentence.lower(), flags=re.UNICODE)
        connectors = cls._discourse.get("connectors", {})
        relation = next((name for name, words in connectors.items() if any(w in tokens for w in words)), None)
        speech_act = "voorstellen" if "voorstel" in tokens or "voor" in tokens and "stel" in tokens else "onbekend"
        domains = [domain for domain in cls._semantics.get("domains", []) if domain.casefold() in tokens]
        return {"surface": sentence, "tokens": tokens, "syntax": cls.parse(sentence),
                "semantics": {"speech_act": speech_act, "domains": domains, "roles": []},
                "discourse": {"relation": relation, "register": "onbekend"}}


def clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


@dataclass
class Individual:
    id: int
    affiliation: int
    opinion: float
    trust: float
    stress: float
    resources: float
    susceptibility: float
    neighbors: list[int] = field(default_factory=list)
    physiology: Physiology = field(default_factory=Physiology)
    life_course: LifeCourse = field(default_factory=LifeCourse)
    assessment: SyntheticAssessment | None = None


@dataclass
class Organization:
    id: int
    name: str
    policy: float
    legitimacy: float
    resources: float
    responsiveness: float


@dataclass(frozen=True)
class DossierEntry:
    step: int
    episode: int
    kind: str
    sender: str
    recipient: str
    topic: str
    message: str
    evidence: str


@dataclass
class Settings:
    social_influence: float = 0.25
    institutional_influence: float = 0.18
    coordination: float = 0.20
    communication: float = 0.50
    noise: float = 0.08
    shock_probability: float = 0.035
    shock_strength: float = 0.35
    trust_adaptation: float = 0.08
    relaxation: float = 0.14
    tolerance: float = 0.007
    stable_window: int = 22
    seed: int = 20261109
    max_steps: int = 2500
    anneal: bool = True
    controversy: float = 0.10
    polarization: float = 0.00
    institutional_alignment: float = 0.50


class Society:
    """Synchronous bounded-state dynamics with periodic perturbation episodes."""
    def __init__(self, settings: Settings):
        self.cfg = settings
        self.rng = random.Random(settings.seed)
        self.episode = 0
        self.step_number = 0
        self.global_step = 0
        self.individuals: list[Individual] = []
        self.organizations: list[Organization] = []
        self.edges: list[tuple[int, int]] = []
        self.history = deque(maxlen=350)
        self.snapshots = deque(maxlen=1200)
        self.transitions = deque(maxlen=400)
        self.communication_log = deque(maxlen=1800)
        self.dossiers = [deque(maxlen=5000) for _ in ORG_NAMES]
        self.dossier_discarded = [0 for _ in ORG_NAMES]
        self.anomalies = deque(maxlen=1200)
        self.log = deque(maxlen=1200)
        self.converged = False
        self.stability_count = 0
        self.last_shock = 0.0
        self._create()
        self._capture_snapshot()

    def _capture_snapshot(self):
        self.snapshots.append((self.global_step, self.episode,
                               copy.deepcopy(self.individuals),
                               copy.deepcopy(self.organizations),
                               list(self.history)))

    def _detect_anomalies(self, mean, spread, delta, policy_gap):
        reasons=[]
        if delta > max(.08, self.cfg.tolerance*12): reasons.append(f"grote toestandsprong Δ={delta:.3f}")
        if spread > .80: reasons.append(f"hoge divergentie spread={spread:.3f}")
        if policy_gap > 1.25: reasons.append(f"grote beleidsafstand={policy_gap:.3f}")
        if len(self.history)>1 and abs(spread-self.history[-2][2])>.18: reasons.append("snelle verandering in spreiding")
        if reasons:
            self.anomalies.append((self.global_step,self.episode,"; ".join(reasons)))

    def _create(self):
        r = self.rng
        self.organizations = [Organization(i, name, r.uniform(-.65, .65), r.uniform(.45, .9),
                                           r.uniform(.35, .95), r.uniform(.45, .9)) for i, name in enumerate(ORG_NAMES)]
        self.individuals = [Individual(i, i % 7, r.uniform(-.9, .9), r.uniform(.3, .9),
                                        r.uniform(.1, .55), r.uniform(.2, .95), r.uniform(.35, .95)) for i in range(37)]
        for ind in self.individuals:
            ind.life_course.age_years = float(ind.id % 19)
            ind.physiology.baseline = .15 + .3 * ind.susceptibility
            ind.physiology.reactivity = .25 + .5 * ind.susceptibility
            self._update_assessment(ind, record=False)
        e = set()
        # Community structure plus cross-organization bridges; the graph is closed.
        for i in range(37):
            candidates = [j for j in range(37) if j != i]
            weights = [3.0 if j % 7 == i % 7 else 1.0 for j in candidates]
            for j in r.choices(candidates, weights=weights, k=5):
                e.add(tuple(sorted((i, j))))
        self.edges = sorted(e)
        for a, b in self.edges:
            self.individuals[a].neighbors.append(b)
            self.individuals[b].neighbors.append(a)
        self._event("INIT", "37 individuen, 7 organisaties en %d sociale verbindingen" % len(self.edges))

    def _event(self, kind, msg):
        self.log.append((self.global_step, self.episode, kind, msg))

    def _update_assessment(self, individual, record=True):
        key = f"assessment:{self.cfg.seed}:{self.episode}:{self.global_step}:{individual.id}"
        raw = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
        error = 2 * raw / (2**64 - 1) - 1
        previous = individual.assessment
        individual.assessment = synthetic_assessment(individual, self.global_step, error)
        current = individual.assessment
        if record and previous is not None and previous.category != current.category:
            self._dossier_entry(individual.affiliation, "Modelinschatting", "Model", f"P{individual.id:02d}",
                "Synthetische observatie", f"Modelcategorie {previous.category} → {current.category}.",
                f"Synthetische observatie {current.observed:.3f}; interval [{current.lower:.3f}, {current.upper:.3f}]. "
                "Alleen een ongetoetst modelvoorbeeld; geen echte meting, diagnose of besluit.")

    def _dossier_entry(self, organization, kind, sender, recipient, topic, message, evidence):
        entries = self.dossiers[organization]
        if len(entries) == entries.maxlen:
            self.dossier_discarded[organization] += 1
        entries.append(DossierEntry(self.global_step, self.episode, kind, sender,
                                    recipient, topic, message, evidence))

    def dossier_entries(self, organization, step, episode, kind="Alles", member="", query=""):
        """Chronological records visible at a snapshot; the same step may span episodes."""
        member, query = member.strip().casefold(), query.strip().casefold()
        return [entry for entry in self.dossiers[organization]
                if (entry.step, entry.episode) <= (step, episode)
                and (kind == "Alles" or entry.kind == kind)
                and (not member or member in entry.sender.casefold() or member in entry.recipient.casefold())
                and (not query or query in (entry.topic + " " + entry.message + " " + entry.evidence).casefold())]

    def new_episode(self, force=False):
        self.episode += 1
        self.step_number = 0
        self.converged = False
        self.stability_count = 0
        self.history.clear()
        strength = self.cfg.shock_strength
        # At every new episode, exogenous changes move the system away from its prior equilibrium.
        for org in self.organizations:
            org.policy = clamp(org.policy + self.rng.uniform(-strength, strength))
            org.resources = max(.05, min(1, org.resources + self.rng.uniform(-strength*.3, strength*.3)))
        for ind in self.individuals:
            ind.opinion = clamp(ind.opinion + self.rng.uniform(-strength*.5, strength*.5))
            ind.stress = max(0, min(1, ind.stress + self.rng.uniform(-strength*.3, strength*.3)))
            self._update_assessment(ind)
        self._event("EPISODE", f"Nieuwe omgevingscondities; schoksterkte={strength:.2f}")

    def step(self):
        c, r = self.cfg, self.rng
        self.step_number += 1
        self.global_step += 1
        old = [i.opinion for i in self.individuals]
        oldp = [o.policy for o in self.organizations]
        shock = r.uniform(-c.shock_strength, c.shock_strength) if r.random() < c.shock_probability else 0.
        self.last_shock = shock
        if shock:
            self._event("SHOCK", f"Gemeenschappelijke externe verstoring {shock:+.3f}")
        # Decaying noise permits convergence despite stochastic exploration.
        temp = max(.002, c.noise / (1 + self.step_number / 45)) if c.anneal else c.noise
        new_op = []
        for i in self.individuals:
            neighbors = [old[j] for j in i.neighbors]
            peer = sum(neighbors)/len(neighbors) if neighbors else old[i.id]
            org = self.organizations[i.affiliation]
            target = ((1-c.social_influence-c.institutional_influence)*old[i.id]
                      + c.social_influence*peer + c.institutional_influence*i.trust*org.legitimacy*oldp[i.affiliation] + c.institutional_influence*(1-i.trust*org.legitimacy)*old[i.id])
            convergence = c.relaxation * i.susceptibility * (0.25 + 0.75*c.communication) * (target - old[i.id])
            divergence = c.controversy * c.polarization * (old[i.id] - peer)
            controversy_noise = r.gauss(0, temp) * (.10 + .35*c.controversy)
            change = convergence + divergence + shock * (0.25 + 0.3*i.susceptibility) + controversy_noise
            new_op.append(clamp(old[i.id] + change))
            for neighbor in sorted(i.neighbors, key=lambda j: abs(old[j] - old[i.id]), reverse=True)[:2]:
                direction = "eensgezind" if abs(old[neighbor] - old[i.id]) < .15 else "verschillend"
                text = DutchGrammar.sentence("ik", old[i.id], i.stress, i.trust, neighbor,
                    step=self.global_step, sender=i.id, recipient_opinion=old[neighbor])
                analysis=DutchGrammar.analyze(text)
                self.communication_log.append((self.global_step, self.episode, f"P{i.id:02d}", f"P{neighbor:02d}",
                    "opinie en vertrouwen", text + f" [{direction}; trefwoordanalyse={len(analysis['tokens'])} woorden]"))
                other_org = self.individuals[neighbor].affiliation
                sender, recipient = f"P{i.id:02d}", f"P{neighbor:02d}"
                evidence = (f"Opinie afzender vóór stap: {old[i.id]:+.4f}; ontvanger: {old[neighbor]:+.4f}; "
                            f"gemiddelde van alle buren: {peer:+.4f}. Getoonde tekst is gegenereerd; "
                            "deze geselecteerde contacten zijn geen afzonderlijk berekende invloed.")
                kind = "Intern gesprek" if other_org == i.affiliation else "Extern gesprek"
                self._dossier_entry(i.affiliation, kind, sender, recipient, "Opinie en vertrouwen", text, evidence)
                if other_org != i.affiliation:
                    self._dossier_entry(other_org, kind, sender, recipient, "Opinie en vertrouwen", text, evidence)
        new_p = []
        for org in self.organizations:
            members = [new_op[i.id] for i in self.individuals if i.affiliation == org.id]
            local = sum(members)/len(members)
            other = sum(oldp[j] for j in range(7) if j != org.id)/6
            target = (1-c.coordination)*local + c.coordination*(c.institutional_alignment*other + (1-c.institutional_alignment)*oldp[org.id])
            new_p.append(clamp(oldp[org.id] + c.relaxation*org.responsiveness*(0.25+0.75*c.communication)*org.resources*(target-oldp[org.id]) + shock*.18))
            self._dossier_entry(org.id, "Terugkoppeling", "Leden (gemiddelde)", org.name,
                "Beleidsupdate", f"Gemiddelde ledenopinie {local:+.4f}; beleid {oldp[org.id]:+.4f} → {new_p[-1]:+.4f}.",
                f"Gemiddeld ander beleid (vorige stap): {other:+.4f}; doel: {target:+.4f}; "
                f"coördinatie: {c.coordination:.4f}; afstemming: {c.institutional_alignment:.4f}; "
                f"responsiviteit: {org.responsiveness:.4f}; middelen: {org.resources:.4f}; schok: {shock:+.4f}. "
                "Dit zijn modelwaarden, geen gemeten menselijke communicatie of causale toeschrijving.")
        delta = max([abs(a-b) for a,b in zip(new_op, old)] + [abs(a-b) for a,b in zip(new_p, oldp)])
        for i, v in zip(self.individuals, new_op):
            prior = i.opinion
            i.opinion = v
            agreement = 1-abs(v-new_p[i.affiliation])/2
            i.trust = max(0, min(1, i.trust + c.trust_adaptation*.03*(agreement-i.trust)))
            i.stress = max(0, min(1, i.stress + .02*(abs(v-prior)*3-i.stress*.18)))
            peer = sum(old[j] for j in i.neighbors) / len(i.neighbors) if i.neighbors else old[i.id]
            i.physiology = physiology_step(i.physiology, i.stress, abs(old[i.id] - peer) / 2, shock)
            i.life_course.advance()
            self._update_assessment(i)
            if abs(v-prior) > .055:
                self.transitions.append((self.global_step, f"P{i.id:02d}", prior, v))
        for o,v in zip(self.organizations, new_p):
            prior = o.policy
            o.policy = v
            if abs(v-prior) > .035:
                self.transitions.append((self.global_step, o.name, prior, v))
        for o in self.organizations:
            self.communication_log.append((self.global_step, self.episode, o.name, "alle leden",
                "beleid en legitimiteit", f"Beleid {o.policy:+.2f}; legitimiteit {o.legitimacy:.2f}; middelen {o.resources:.2f}."))
            self._dossier_entry(o.id, "Organisatiebericht", o.name, "alle leden", "Beleid en legitimiteit",
                f"Beleid {o.policy:+.4f}; legitimiteit {o.legitimacy:.4f}; middelen {o.resources:.4f}.",
                "Synthetische samenvatting van de organisatietoestand na de beleidsupdate.")
        vals = new_op + new_p
        mean = sum(new_op)/37
        spread = math.sqrt(sum((v-mean)**2 for v in new_op)/37)
        policy_gap = max(new_p)-min(new_p)
        self.history.append((self.global_step, mean, spread, delta, policy_gap))
        self._detect_anomalies(mean, spread, delta, policy_gap)
        self.stability_count = self.stability_count + 1 if delta < c.tolerance and not shock else 0
        self.converged = self.stability_count >= c.stable_window
        if self.global_step % 12 == 0:
            self._event("METRIC", f"μ={mean:+.3f} σ={spread:.3f} Δ={delta:.5f} beleidsafstand={policy_gap:.3f} stabiel={self.stability_count}/{c.stable_window}")
        if self.converged:
            self._event("STABLE", f"Evenwicht episode {self.episode}: Δ<{c.tolerance} gedurende {c.stable_window} stappen; σ={spread:.3f}")
        elif self.step_number >= c.max_steps:
            self._event("TIMEOUT", f"Episode {self.episode} niet geconvergeerd binnen {c.max_steps} stappen")
        self._capture_snapshot()
        return self.converged or self.step_number >= c.max_steps


class SimulatorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Digital Society Simulator | 7 organisaties · 37 individuen")
        self.geometry("1500x940")
        self.minsize(1080, 700)
        self.configure(bg=BG)
        self.cfg = Settings()
        self.sim = Society(self.cfg)
        self.running = False
        self.auto_episodes = tk.BooleanVar(value=True)
        self.vars = {}
        self._ui()
        self._refresh()
        self.after(60, self._tick)

    def _ui(self):
        self.option_add("*Font", ("Segoe UI", 10))
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("TNotebook", background=BG)
        style.configure("TNotebook.Tab", padding=(6,8))
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=25)
        style.configure("Treeview.Heading", background="#203047", foreground=FG)
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        head = tk.Frame(self, bg=BG)
        head.grid(row=0,column=0,columnspan=2,sticky="ew",padx=14,pady=12)
        tk.Label(head,text="DIGITAL SOCIETY  /  CYBERNETIC LAB",fg=FG,bg=BG,font=("Segoe UI",18,"bold")).pack(side="left")
        self.status = tk.Label(head,text="GEREED",fg="#34d399",bg=BG,font=("Consolas",11,"bold"))
        self.status.pack(side="right")
        left = tk.Frame(self,bg=BG)
        left.grid(row=1,column=1,sticky="nsew",padx=(6,14),pady=(0,14))
        left.rowconfigure(0,weight=3)
        left.rowconfigure(1,weight=2)
        left.rowconfigure(2,weight=0)
        left.columnconfigure(0,weight=1)
        top = ttk.Notebook(left)
        self.top_notebook = top
        top.grid(row=0,column=0,sticky="nsew")
        network = tk.Frame(top,bg=PANEL)
        metrics = tk.Frame(top,bg=PANEL)
        states = tk.Frame(top,bg=PANEL)
        individuals_view = tk.Frame(top,bg=PANEL)
        organizations_view = tk.Frame(top,bg=PANEL)
        dossier_view = tk.Frame(top,bg=PANEL)
        inspect_view = tk.Frame(top,bg=PANEL)
        relation_view = tk.Frame(top,bg=PANEL)
        lab_view = tk.Frame(top,bg=PANEL)
        self.individual_tab, self.dossier_tab = individuals_view, dossier_view
        top.add(network,text="Netwerk")
        top.add(metrics,text="Metrieken")
        top.add(states,text="Toestanden")
        top.add(individuals_view,text="Personen")
        top.add(organizations_view,text="Organisaties")
        top.add(dossier_view,text="Dossiers")
        top.add(inspect_view,text="Inspectie")
        top.add(relation_view,text="Relaties")
        top.add(lab_view,text="Model Lab")
        lab = ttk.Notebook(lab_view); lab.pack(fill="both", expand=True)
        physiology_view = tk.Frame(lab,bg=PANEL)
        formal_view = tk.Frame(lab,bg=PANEL)
        language_view = tk.Frame(lab,bg=PANEL)
        spatial_view = tk.Frame(lab,bg=PANEL)
        for view,title in ((physiology_view,"Fysiologie"),(formal_view,"Formeel model"),
                           (language_view,"Nederlandse grammatica"),(spatial_view,"3D toestandsruimte")):
            lab.add(view,text=title)
        self._build_physiology(physiology_view)
        self._build_formal_view(formal_view)
        self._build_language_view(language_view)
        self._build_spatial_view(spatial_view)
        self.network_canvas = tk.Canvas(network,bg=PANEL,highlightthickness=0)
        self.network_canvas.pack(fill="both",expand=True)
        self.metric_canvas = tk.Canvas(metrics,bg=PANEL,highlightthickness=0)
        self.metric_canvas.pack(fill="both",expand=True)
        self._enable_diagram_navigation(self.network_canvas)
        self._enable_diagram_navigation(self.metric_canvas)
        nav=tk.Frame(individuals_view,bg=PANEL); nav.pack(side="left",fill="y")
        self.individual_list=tk.Listbox(nav,bg="#17263a",fg=FG,selectbackground="#31577e",width=24,relief="flat")
        self.individual_list.pack(fill="y",expand=True,padx=8,pady=8)
        self.individual_list.bind("<<ListboxSelect>>",lambda _ : self._refresh_individual_dashboard())
        self.individual_canvas=tk.Canvas(individuals_view,bg=PANEL,highlightthickness=0)
        self.individual_canvas.pack(side="left",fill="both",expand=True)
        self._enable_diagram_navigation(self.individual_canvas)
        self.organization_canvas = tk.Canvas(organizations_view,bg=PANEL,highlightthickness=0)
        self.organization_canvas.pack(fill="both",expand=True)
        self._enable_diagram_navigation(self.organization_canvas)
        self._build_dossier(dossier_view)
        self.inspect_tree=ttk.Treeview(inspect_view,columns=("path","value"),show="headings")
        self.inspect_tree.heading("path",text="Toestandsprimitief / logveld"); self.inspect_tree.heading("value",text="Waarde")
        self.inspect_tree.column("path",width=300); self.inspect_tree.column("value",width=700)
        self.inspect_tree.pack(fill="both",expand=True,padx=8,pady=8)
        relbar=tk.Frame(relation_view,bg=PANEL); relbar.pack(fill="x",padx=10,pady=8)
        tk.Label(relbar,text="Entiteit A",bg=PANEL,fg=MUTED).pack(side="left")
        self.rel_a=tk.StringVar(value="P00")
        self.rel_a_combo=ttk.Combobox(relbar,textvariable=self.rel_a,state="readonly",width=22); self.rel_a_combo.pack(side="left",padx=5)
        tk.Label(relbar,text="Entiteit B",bg=PANEL,fg=MUTED).pack(side="left",padx=(12,0))
        self.rel_b=tk.StringVar(value="P01")
        self.rel_b_combo=ttk.Combobox(relbar,textvariable=self.rel_b,state="readonly",width=22); self.rel_b_combo.pack(side="left",padx=5)
        self.show_org_var=tk.BooleanVar(value=True)
        tk.Checkbutton(relbar,text="Organisaties tonen",variable=self.show_org_var,bg=PANEL,fg=FG,selectcolor="#243850",activebackground=PANEL,command=self._refresh_relation_choices).pack(side="left",padx=10)
        self.rel_a_combo.bind("<<ComboboxSelected>>",lambda _:self._draw_relationships())
        self.rel_b_combo.bind("<<ComboboxSelected>>",lambda _:self._draw_relationships())
        self.relationship_canvas=tk.Canvas(relation_view,bg=PANEL,highlightthickness=0); self.relationship_canvas.pack(fill="both",expand=True)
        self._enable_diagram_navigation(self.relationship_canvas)
        columns=("id","org","opinion","trust","stress","resources")
        self.state_tree=ttk.Treeview(states,columns=columns,show="headings")
        for k,label,width in zip(columns,["Actor","Organisatie","Opinie","Vertrouwen","Stress","Middelen"],[75,190,105,110,100,110]):
            self.state_tree.heading(k,text=label)
            self.state_tree.column(k,width=width,anchor="center")
        self.state_tree.pack(fill="both",expand=True)
        bottom = ttk.Notebook(left)
        bottom.grid(row=1,column=0,sticky="nsew",pady=(9,0))
        logframe=tk.Frame(bottom,bg=PANEL)
        transframe=tk.Frame(bottom,bg=PANEL)
        commframe=tk.Frame(bottom,bg=PANEL)
        anomalyframe=tk.Frame(bottom,bg=PANEL)
        bottom.add(logframe,text="  LIVE LOGTAIL  ")
        bottom.add(transframe,text="  STATE TRANSITIONS  ")
        bottom.add(commframe,text="  COMMUNICATIELOG  ")
        bottom.add(anomalyframe,text="  ANOMALIEËN  ")
        self.logbox=tk.Text(logframe,bg=PANEL,fg="#b9d6f0",font=("Consolas",10),wrap="none",relief="flat")
        self.logbox.pack(fill="both",expand=True)
        self.transbox=tk.Text(transframe,bg=PANEL,fg="#b9d6f0",font=("Consolas",10),wrap="none",relief="flat")
        self.transbox.pack(fill="both",expand=True)
        self.comm_box=tk.Text(commframe,bg=PANEL,fg="#b9d6f0",font=("Consolas",9),wrap="none",relief="flat")
        self.comm_box.pack(fill="both",expand=True)
        self.anomaly_box=tk.Text(anomalyframe,bg=PANEL,fg="#ffd2a6",font=("Consolas",9),wrap="none",relief="flat")
        self.anomaly_box.pack(fill="both",expand=True)
        self._build_trace_footer(left)
        right=tk.Frame(self,bg=PANEL,width=335)
        right.grid(row=1,column=0,sticky="ns",padx=(14,6),pady=(0,14))
        right.grid_propagate(False)
        canvas=tk.Canvas(right,bg=PANEL,highlightthickness=0,width=335)
        scroll=ttk.Scrollbar(right,orient="vertical",command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left",fill="both",expand=True)
        scroll.pack(side="right",fill="y")
        controls=tk.Frame(canvas,bg=PANEL)
        win=canvas.create_window((0,0),window=controls,anchor="nw")
        controls.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda e:canvas.itemconfigure(win,width=e.width))
        tk.Label(controls,text="CONTROLEPANEEL",bg=PANEL,fg=FG,font=("Segoe UI",13,"bold")).pack(anchor="w",padx=15,pady=(16,9))
        row=tk.Frame(controls,bg=PANEL)
        row.pack(fill="x",padx=12,pady=4)
        for text,action in [("▶ Start",self.start),("Ⅱ Pauze",self.pause),("↻ Reset",self.reset)]:
            tk.Button(row,text=text,command=action,bg="#243850",fg=FG,activebackground="#385477",relief="flat",padx=8,pady=9).pack(side="left",expand=True,fill="x",padx=2)
        tk.Button(controls,text="Eén stap uitvoeren",command=self.one_step,bg="#243850",fg=FG,relief="flat",pady=8).pack(fill="x",padx=14,pady=4)
        tk.Button(controls,text="Nieuwe omgevings-episode",command=self.new_episode,bg="#243850",fg=FG,relief="flat",pady=8).pack(fill="x",padx=14,pady=4)
        tk.Label(controls,text="GEWENSTE TOESTAND",bg=PANEL,fg=FG,font=("Segoe UI",11,"bold")).pack(anchor="w",padx=14,pady=(14,3))
        self.target_mean=tk.DoubleVar(value=0.0); self.target_spread=tk.DoubleVar(value=.25); self.target_gap=tk.DoubleVar(value=.35)
        for label,var,lo,hi in [("Gemiddelde opinie",self.target_mean,-1,1),("Gewenste spreiding",self.target_spread,0,1),("Maximale beleidsafstand",self.target_gap,0,2)]:
            f=tk.Frame(controls,bg=PANEL); f.pack(fill="x",padx=14,pady=2)
            tk.Label(f,text=label,bg=PANEL,fg=MUTED).pack(anchor="w")
            tk.Scale(f,from_=lo,to=hi,variable=var,resolution=.01,orient="horizontal",bg=PANEL,fg=FG,highlightthickness=0,troughcolor="#31435b").pack(fill="x")
        tk.Button(controls,text="Optimaliseer parameters",command=self.optimize,bg="#326b55",fg=FG,relief="flat",pady=10).pack(fill="x",padx=14,pady=(8,4))
        regime=tk.Frame(controls,bg=PANEL); regime.pack(fill="x",padx=12,pady=(3,8))
        tk.Button(regime,text="Stabiel",command=lambda:self.set_regime("stable"),bg="#24516b",fg=FG,relief="flat").pack(side="left",expand=True,fill="x",padx=2)
        tk.Button(regime,text="Chaos",command=lambda:self.set_regime("chaos"),bg="#7a3f52",fg=FG,relief="flat").pack(side="left",expand=True,fill="x",padx=2)
        tk.Label(controls,text="Random coordinate search · doel = toestand benaderen",bg=PANEL,fg=MUTED,font=("Segoe UI",9)).pack(anchor="w",padx=14)
        self._slider(controls,"social_influence","Sociale beïnvloeding",0,.75,.25)
        self._slider(controls,"institutional_influence","Institutionele invloed",0,.75,.18)
        self._slider(controls,"coordination","Interorganisationele coördinatie",0,1,.2)
        self._slider(controls,"communication","Communicatiesnelheid",.05,1,.5)
        self._slider(controls,"noise","Willekeurige ruis",0,.5,.08)
        self._slider(controls,"shock_probability","Schokkans per stap",0,.25,.035)
        self._slider(controls,"shock_strength","Sterkte van verstoringen",0,.9,.35)
        self._slider(controls,"trust_adaptation","Vertrouwensadaptatie",0,.5,.08)
        self._slider(controls,"relaxation","Aanpassingssnelheid",.01,.8,.14)
        tk.Label(controls,text="DIVERGENTIE & REGIME",bg=PANEL,fg=FG,font=("Segoe UI",11,"bold")).pack(anchor="w",padx=14,pady=(12,2))
        self._slider(controls,"controversy","Controversie / ruisversterking",0,1,.10)
        self._slider(controls,"polarization","Polarisatie / uiteen trekken",0,1,0.0)
        self._slider(controls,"institutional_alignment","Institutionele afstemming",0,1,.50)
        self._slider(controls,"tolerance","Convergentiedrempel",.001,.04,.007, digits=4)
        self._slider(controls,"stable_window","Stabiele opeenvolgende stappen",5,80,22,integer=True)
        tk.Checkbutton(controls,text="Automatisch nieuwe episodes",variable=self.auto_episodes,bg=PANEL,fg=FG,selectcolor="#243850",activebackground=PANEL).pack(anchor="w",padx=14,pady=8)
        self.anneal_var=tk.BooleanVar(value=True)
        tk.Checkbutton(controls,text="Ruis geleidelijk verminderen",variable=self.anneal_var,command=self._apply,bg=PANEL,fg=FG,selectcolor="#243850",activebackground=PANEL).pack(anchor="w",padx=14)
        self.speed_var=tk.IntVar(value=8)
        tk.Label(controls,text="Simulatiestappen per UI-tick",bg=PANEL,fg=MUTED).pack(anchor="w",padx=14,pady=(10,0))
        tk.Scale(controls,from_=1,to=100,orient="horizontal",variable=self.speed_var,bg=PANEL,fg=FG,highlightthickness=0,troughcolor="#31435b").pack(fill="x",padx=12)
        tk.Button(controls,text="Exporteer CSV metrieken",command=self.export_csv,bg="#24516b",fg=FG,relief="flat",pady=10).pack(fill="x",padx=14,pady=(12,5))
        tk.Button(controls,text="Exporteer logbestand",command=self.export_log,bg="#24516b",fg=FG,relief="flat",pady=10).pack(fill="x",padx=14,pady=(0,16))

    def _slider(self,parent,key,label,lo,hi,default,digits=3,integer=False):
        v=tk.IntVar(value=int(default)) if integer else tk.DoubleVar(value=default)
        self.vars[key]=v
        f=tk.Frame(parent,bg=PANEL)
        f.pack(fill="x",padx=13,pady=(7,0))
        tk.Label(f,text=label,bg=PANEL,fg=MUTED,font=("Segoe UI",9)).pack(anchor="w")
        tk.Scale(f,from_=lo,to=hi,resolution=1 if integer else (.001 if digits==4 else .01),orient="horizontal",variable=v,
                 command=lambda _=None:self._apply(),bg=PANEL,fg=FG,highlightthickness=0,troughcolor="#31435b",length=290).pack(fill="x")

    def _apply(self):
        for key,var in self.vars.items():
            setattr(self.cfg,key,var.get())
        self.cfg.anneal=self.anneal_var.get()
        # Keep convex opinion targets; otherwise high sliders can produce overshooting.
        total=self.cfg.social_influence+self.cfg.institutional_influence
        if total>1:
            self.cfg.social_influence/=total
            self.cfg.institutional_influence/=total

    def start(self):
        self.running=True
        self.trace_index = -1
    def pause(self):
        self.running=False
        self.trace_index = -1
    def reset(self):
        self.running=False
        self.sim=Society(self.cfg)
        self.trace_index = -1
        self._refresh()
    def new_episode(self):
        self.running=False
        self.sim.new_episode()
        self.sim._capture_snapshot()
        self.trace_index = -1
        self._refresh()
    def one_step(self):
        self._apply()
        if self.sim.step():
            self.running=False
        self._refresh()

    def _build_trace_footer(self, parent):
        footer=tk.Frame(parent,bg=PANEL)
        footer.grid(row=2,column=0,sticky="ew",pady=(9,0))
        footer.columnconfigure(1,weight=1)
        tk.Label(footer,text="TRACEBACK",bg=PANEL,fg=FG,font=("Segoe UI",10,"bold")).grid(row=0,column=0,padx=(10,8),pady=6)
        self.trace_var=tk.IntVar(value=0)
        self.trace_scale=tk.Scale(footer,from_=0,to=0,orient="horizontal",variable=self.trace_var,showvalue=False,command=self._trace_changed,bg=PANEL,fg=FG,highlightthickness=0,troughcolor="#31435b")
        self.trace_scale.grid(row=0,column=1,sticky="ew",padx=4)
        self.trace_label=tk.Label(footer,text="t=0",bg=PANEL,fg=MUTED,font=("Consolas",9),width=18)
        self.trace_label.grid(row=0,column=2,padx=6)
        tk.Button(footer,text="◀",command=lambda:self._move_trace(-1),bg="#243850",fg=FG,relief="flat",width=3).grid(row=0,column=3,padx=2)
        tk.Button(footer,text="▶",command=lambda:self._move_trace(1),bg="#243850",fg=FG,relief="flat",width=3).grid(row=0,column=4,padx=2)

    def _move_trace(self,delta):
        if not self.sim.snapshots:return
        self.running=False
        idx=max(0,min(len(self.sim.snapshots)-1,self.trace_var.get()+delta))
        self.trace_var.set(idx)
        self._trace_changed()

    def _trace_changed(self,_=None):
        self.running=False
        self.trace_index=max(0,min(len(self.sim.snapshots)-1,self.trace_var.get()))
        self._refresh()

    def optimize(self):
        """Bounded random coordinate search over influential settings."""
        self.running=False; base=copy.deepcopy(self.cfg)
        keys=["social_influence","institutional_influence","coordination","communication","relaxation"]
        bounds={"social_influence":(.02,.75),"institutional_influence":(.02,.75),"coordination":(0,1),"communication":(.05,1),"relaxation":(.01,.8)}
        def score(cfg):
            probe=Society(cfg)
            for _ in range(28): probe.step()
            h=probe.history[-1]
            return abs(h[1]-self.target_mean.get())+abs(h[2]-self.target_spread.get())+abs(h[4]-self.target_gap.get())
        best=base; best_score=score(base); rng=random.Random(self.cfg.seed+17)
        for _ in range(24):
            candidate=copy.deepcopy(best); key=rng.choice(keys); lo,hi=bounds[key]
            setattr(candidate,key,max(lo,min(hi,getattr(candidate,key)+rng.uniform(-.12,.12))))
            candidate.seed += rng.randrange(1,100000)
            value=score(candidate)
            if value < best_score: best,best_score=candidate,value
        self.cfg=best
        for key,var in self.vars.items(): var.set(getattr(self.cfg,key))
        self.sim._event("OPTIMIZE",f"Parameterschatting voltooid; foutscore={best_score:.4f}")
        self._refresh()

    def set_regime(self, regime):
        values = {"stable": {"controversy": .02, "polarization": 0.0, "shock_probability": .005, "noise": .015, "relaxation": .20, "institutional_alignment": .85},
                  "chaos": {"controversy": .85, "polarization": .90, "shock_probability": .18, "noise": .35, "relaxation": .08, "institutional_alignment": .10}}
        for key,value in values[regime].items():
            setattr(self.cfg,key,value)
            if key in self.vars: self.vars[key].set(value)
        self.sim._event("REGIME",f"Regime ingesteld: {regime}; divergentie={self.cfg.polarization:.2f}, controversie={self.cfg.controversy:.2f}")
        self._refresh()

    def _tick(self):
        if self.running:
            self._apply()
            for _ in range(self.speed_var.get()):
                finished=self.sim.step()
                if finished:
                    if self.auto_episodes.get():
                        self.sim.new_episode()
                        self.sim._capture_snapshot()
                    else:
                        self.running=False
                        break
            self._refresh()
        self.after(100,self._tick)

    def _refresh(self):
        s=self.sim
        if s.snapshots:
            self.trace_scale.configure(to=len(s.snapshots)-1)
        idx = self.trace_index if getattr(self, "trace_index", -1) >= 0 else len(s.snapshots)-1
        idx = max(0, min(len(s.snapshots)-1, idx))
        snap = s.snapshots[idx]
        step, episode, individuals, organizations, history = snap
        self.trace_var.set(idx)
        self.trace_label.config(text=f"t={step}  E{episode:03d}  ({idx+1}/{len(s.snapshots)})")
        last=s.history[-1] if s.history else (0,0,0,0,0)
        self.status.config(text=f"{'ACTIEF' if self.running else 'PAUZE'}  |  EPISODE {s.episode}  |  STAP {s.global_step}  |  Δ {last[3]:.5f}  |  STABILITEIT {s.stability_count}/{self.cfg.stable_window}")
        if s.anomalies and s.anomalies[-1][0] == step:
            self.status.config(fg="#fb7185")
        else:
            self.status.config(fg="#34d399" if not self.running else "#fbbf24")
        self._draw_network()
        self._draw_metrics(history, step)
        self._draw_individuals(individuals, step)
        self._draw_organizations(organizations, step)
        current_selection=self.individual_list.curselection()
        self.individual_list.delete(0,"end")
        for i in individuals:
            self.individual_list.insert("end",f"P{i.id:02d} · {ORG_NAMES[i.affiliation]}")
        if current_selection and current_selection[0] < len(individuals):
            self.individual_list.selection_set(current_selection[0])
        elif individuals:
            self.individual_list.selection_set(0)
        self._refresh_individual_dashboard()
        self._refresh_relation_choices(individuals, organizations)
        self._refresh_dossier()
        self._refresh_lab()
        self.inspect_tree.delete(*self.inspect_tree.get_children())
        primitive=[("time.step",step),("time.episode",episode),("population.individuals",len(individuals)),("population.organizations",len(organizations)),
                   ("metrics.history_length",len(history)),("metrics.last_mean",history[-1][1] if history else "—"),
                   ("metrics.last_spread",history[-1][2] if history else "—"),("metrics.last_delta",history[-1][3] if history else "—"),
                   ("metrics.policy_gap",history[-1][4] if history else "—"),("logs.communications_total",len(s.communication_log)),
                   ("logs.transitions_total",len(s.transitions)),("logs.events_total",len(s.log))]
        for path,value in primitive: self.inspect_tree.insert("","end",values=(path,value))
        self.state_tree.delete(*self.state_tree.get_children())
        for i in individuals:
            self.state_tree.insert("", "end", values=(f"P{i.id:02d}",ORG_NAMES[i.affiliation],f"{i.opinion:+.3f}",f"{i.trust:.3f}",f"{i.stress:.3f}",f"{i.resources:.3f}"))
        for o in organizations:
            self.state_tree.insert("", "end",values=(f"O{o.id}",o.name,f"{o.policy:+.3f}",f"{o.legitimacy:.3f}","—",f"{o.resources:.3f}"))
        self._update_text(self.logbox,[f"[{step:06d} / E{ep:03d}] {kind:8} {msg}" for step,ep,kind,msg in list(s.log)[-220:]])
        self._update_text(self.transbox,[f"[{step:06d}] {who:22} {old:+.4f} → {new:+.4f}  (Δ {new-old:+.4f})" for step,who,old,new in list(s.transitions)[-250:]])

        comms=[x for x in s.communication_log if x[0] <= step][-180:]
        self._update_text(self.comm_box,[f"[{st:06d}/E{ep:03d}] {src:18} -> {dst:18} | {topic}: {message}" for st,ep,src,dst,topic,message in comms])
        self._update_text(self.anomaly_box,[f"[{st:06d}/E{ep:03d}] {reason}" for st,ep,reason in list(s.anomalies)[-220:]])

    def _update_text(self,widget,lines):
        widget.configure(state="normal")
        widget.delete("1.0","end")
        widget.insert("end","\n".join(lines))
        widget.see("end")
        widget.configure(state="disabled")

    def _enable_diagram_navigation(self, canvas):
        canvas._zoom_factor = 1.0
        canvas.configure(scrollregion=(-4000, -4000, 8000, 8000))
        def zoom(event):
            direction = 1 if getattr(event, "delta", 0) > 0 or getattr(event, "num", 0) == 4 else -1
            old = canvas._zoom_factor
            canvas._zoom_factor = max(.4, min(4.0, old * (1.12 if direction > 0 else 1 / 1.12)))
            canvas.scale("all", canvas.canvasx(event.x), canvas.canvasy(event.y), canvas._zoom_factor / old, canvas._zoom_factor / old)
            return "break"
        canvas.bind("<MouseWheel>", zoom)
        canvas.bind("<Button-4>", zoom); canvas.bind("<Button-5>", zoom)
        canvas.bind("<ButtonPress-2>", lambda e: canvas.scan_mark(e.x, e.y))
        canvas.bind("<B2-Motion>", lambda e: canvas.scan_dragto(e.x, e.y, gain=1))
        canvas.bind("<ButtonPress-3>", lambda e: canvas.scan_mark(e.x, e.y))
        canvas.bind("<B3-Motion>", lambda e: canvas.scan_dragto(e.x, e.y, gain=1))

    def _apply_diagram_zoom(self, canvas):
        scale = getattr(canvas, "_zoom_factor", 1.0)
        if scale != 1.0:
            canvas.scale("all", max(1,canvas.winfo_width()) / 2, max(1,canvas.winfo_height()) / 2, scale, scale)

    def _open_individual(self, index):
        self.individual_list.selection_clear(0, "end")
        self.individual_list.selection_set(index); self.individual_list.see(index)
        self.phys_person.set(f"P{index:02d}")
        self._load_physiology_parameters()
        self.top_notebook.select(self.individual_tab)
        self._refresh_individual_dashboard()

    def _open_organization(self, index):
        self.dossier_org.set(ORG_NAMES[index]); self.dossier_page = 0
        self.top_notebook.select(self.dossier_tab); self._refresh_dossier()

    def _build_physiology(self, parent):
        toolbar = tk.Frame(parent,bg=PANEL); toolbar.pack(fill="x",padx=8,pady=4)
        tk.Label(toolbar,text="Persoon",bg=PANEL,fg=FG).pack(side="left")
        self.phys_person = tk.StringVar(value="P00")
        combo = ttk.Combobox(toolbar,textvariable=self.phys_person,state="readonly",width=7,
                             values=[f"P{i:02d}" for i in range(37)])
        combo.pack(side="left",padx=5); combo.bind("<<ComboboxSelected>>",lambda e:self._load_physiology_parameters())
        tk.Label(toolbar,text="Dimensieloos, synthetisch · geen klinische metingen",bg=PANEL,fg=MUTED).pack(side="left",padx=8)
        self.phys_values = {}
        sliders = tk.Frame(parent,bg=PANEL); sliders.pack(fill="x")
        for key,label,maximum in (("baseline","Basisniveau",1),("reactivity","Reactiviteit",1),("regulation","Regulatie",1),("sleep_support","Herstelondersteuning",1),("observation_uncertainty","Observatie-onzekerheid",.25)):
            var = tk.DoubleVar(value=getattr(Physiology(),key)); self.phys_values[key] = var
            group = tk.Frame(sliders,bg=PANEL); group.pack(side="left",fill="x",expand=True,padx=4)
            tk.Label(group,text=label,bg=PANEL,fg=MUTED).pack(anchor="w")
            tk.Scale(group,from_=0,to=maximum,resolution=.01,orient="horizontal",variable=var,bg=PANEL,fg=FG,highlightthickness=0).pack(fill="x")
        actions=tk.Frame(parent,bg=PANEL); actions.pack(fill="x",padx=8)
        tk.Button(actions,text="Laad geselecteerd",command=self._load_physiology_parameters).pack(side="left")
        tk.Button(actions,text="Pas toe op actuele toestand",command=self._apply_physiology_parameters).pack(side="left",padx=6)
        self.phys_status = tk.Label(actions,text="",bg=PANEL,fg=MUTED); self.phys_status.pack(side="left",padx=6)
        self.phys_canvas = tk.Canvas(parent,bg=PANEL,highlightthickness=0); self.phys_canvas.pack(fill="both",expand=True)
        self._enable_diagram_navigation(self.phys_canvas)

    def _load_physiology_parameters(self):
        ind=self._selected_snapshot()[2][int(self.phys_person.get()[1:])]
        for key,var in self.phys_values.items(): var.set(getattr(ind.physiology,key))
        self._refresh_lab()

    def _apply_physiology_parameters(self):
        if self.running or (getattr(self,"trace_index",-1) >= 0 and self.trace_index != len(self.sim.snapshots)-1):
            self.phys_status.config(text="Pauzeer en selecteer de nieuwste snapshot.",fg="#fb7185"); return
        ind=self.sim.individuals[int(self.phys_person.get()[1:])]
        for key,var in self.phys_values.items(): setattr(ind.physiology,key,var.get())
        self.sim._update_assessment(ind)
        self.sim._event("FYSIO",f"P{ind.id:02d}: fysiologische parameters gewijzigd")
        self.sim._capture_snapshot(); self.trace_index=-1
        self.phys_status.config(text="Toegepast op actuele toestand",fg="#34d399"); self._refresh()

    def _build_formal_view(self, parent):
        self.formal_text = tk.Text(parent,bg=PANEL,fg=FG,wrap="word",font=("Consolas",10),relief="flat")
        self.formal_text.pack(fill="both",expand=True,padx=10,pady=10)

    def _build_language_view(self, parent):
        bar=tk.Frame(parent,bg=PANEL); bar.pack(fill="x",padx=10,pady=8)
        self.grammar_input=tk.StringVar(value="Vandaag leest de student het boek.")
        entry=tk.Entry(bar,textvariable=self.grammar_input); entry.pack(side="left",fill="x",expand=True)
        tk.Button(bar,text="Analyseer",command=self._analyze_formal_sentence).pack(side="left",padx=5)
        entry.bind("<Return>",lambda e:self._analyze_formal_sentence())
        tk.Label(parent,text="Beperkt lexicon: V2, inversie, vragen, overeenkomst, dat-recursie en werkwoordfinale bijzinnen.",bg=PANEL,fg=MUTED).pack(anchor="w",padx=10)
        self.grammar_tree=ttk.Treeview(parent,columns=("value",),show="tree headings")
        self.grammar_tree.heading("#0",text="Constituent / kenmerk"); self.grammar_tree.heading("value",text="Waarde")
        self.grammar_tree.pack(fill="both",expand=True,padx=10,pady=8)
        self._analyze_formal_sentence()

    def _analyze_formal_sentence(self):
        self.grammar_tree.delete(*self.grammar_tree.get_children())
        try: tree=FORMAL_DUTCH.parse(self.grammar_input.get())
        except FragmentError as exc:
            self.grammar_tree.insert("","end",text="Buiten ondersteund fragment",values=(str(exc),)); return
        def add(parent, obj):
            for key,value in obj.items():
                if isinstance(value,dict):
                    child=self.grammar_tree.insert(parent,"end",text=key,open=True); add(child,value)
                else: self.grammar_tree.insert(parent,"end",text=key,values=(value,))
        add("",tree)

    def _build_spatial_view(self, parent):
        bar=tk.Frame(parent,bg=PANEL); bar.pack(fill="x",padx=8)
        self.spatial_angle=tk.DoubleVar(value=35)
        self.spatial_selected=None
        tk.Label(bar,text="Rotatie",bg=PANEL,fg=FG).pack(side="left")
        tk.Scale(bar,from_=-180,to=180,orient="horizontal",variable=self.spatial_angle,command=lambda _:self._draw_spatial(),bg=PANEL,fg=FG,highlightthickness=0,length=200).pack(side="left")
        tk.Label(bar,text="X opinie · Y stress · Z activatie | klik: selecteer",bg=PANEL,fg=MUTED).pack(side="left",padx=8)
        tk.Button(bar,text="Open dashboard",command=lambda:self._open_individual(self.spatial_selected) if self.spatial_selected is not None else None).pack(side="right")
        filters=tk.Frame(parent,bg=PANEL); filters.pack(fill="x",padx=8)
        self.spatial_orgs=[]
        for index,name in enumerate(ORG_NAMES):
            var=tk.BooleanVar(value=True); self.spatial_orgs.append(var)
            tk.Checkbutton(filters,text=name,variable=var,command=self._draw_spatial,bg=PANEL,
                           fg=ORG_COLORS[index],selectcolor="#243850",activebackground=PANEL).pack(side="left")
        self.spatial_info=tk.Label(parent,text="Selecteer een knoop · wiel: zoom · rechts slepen: verplaats",bg=PANEL,fg=MUTED,anchor="w")
        self.spatial_info.pack(fill="x",padx=8)
        self.spatial_canvas=tk.Canvas(parent,bg=PANEL,highlightthickness=0); self.spatial_canvas.pack(fill="both",expand=True)
        self._enable_diagram_navigation(self.spatial_canvas)
        self.spatial_canvas.bind("<Configure>",lambda e:self._draw_spatial())

    def _draw_spatial(self):
        if not hasattr(self,"spatial_canvas"): return
        c=self.spatial_canvas; c.delete("all"); snap=self._selected_snapshot()
        w=max(400,c.winfo_width()); h=max(250,c.winfo_height()); angle=math.radians(self.spatial_angle.get())
        def project(x,y,z):
            rx=x*math.cos(angle)-y*math.sin(angle); ry=x*math.sin(angle)+y*math.cos(angle)
            return w/2+rx*min(w,h)*.34, h*.57-ry*min(w,h)*.16-z*min(w,h)*.32
        origin=project(0,0,0)
        for axis,end,color in (("opinie",(1,0,0),"#60a5fa"),("stress",(0,1,0),"#fb7185"),("activatie",(0,0,1),"#34d399")):
            x,y=project(*end); c.create_line(*origin,x,y,fill=color,width=2,arrow="last"); c.create_text(x,y,text=axis,fill=color,anchor="sw")
        for i in snap[2]:
            if not self.spatial_orgs[i.affiliation].get(): continue
            x,y=project(i.opinion, i.stress, i.physiology.activation)
            tag=f"spatial_{i.id}"; selected=i.id==self.spatial_selected; radius=9 if selected else 6
            c.create_oval(x-radius,y-radius,x+radius,y+radius,fill=ORG_COLORS[i.affiliation],outline="#ffffff" if selected else FG,width=3 if selected else 1,tags=(tag,))
            if selected: c.create_text(x+10,y-10,text=f"P{i.id:02d}",anchor="w",fill=FG,tags=(tag,))
            c.tag_bind(tag,"<Button-1>",lambda e,index=i.id:self._select_spatial(index))
            c.tag_bind(tag,"<Double-Button-1>",lambda e,index=i.id:self._open_individual(index))
        c.create_text(10,15,anchor="w",text=f"Synthetische toestand · t={snap[0]} · E{snap[1]}",fill=FG)
        if self.spatial_selected is not None:
            ind=snap[2][self.spatial_selected]
            self.spatial_info.config(text=f"P{ind.id:02d} · {ORG_NAMES[ind.affiliation]} · opinie {ind.opinion:+.3f} · stress {ind.stress:.3f} · activatie {ind.physiology.activation:.3f} · modelobservatie {ind.assessment.observed:.3f}")
        self._apply_diagram_zoom(c)

    def _select_spatial(self, index):
        self.spatial_selected=index
        self.phys_person.set(f"P{index:02d}")
        self._load_physiology_parameters()

    def _refresh_lab(self):
        if not hasattr(self,"phys_canvas"): return
        step,episode,individuals,orgs,_=self._selected_snapshot()
        index=int(self.phys_person.get()[1:]); ind=individuals[index]; p=ind.physiology
        c=self.phys_canvas; c.delete("all"); w=max(450,c.winfo_width()); h=max(160,c.winfo_height())
        c.create_text(15,18,anchor="w",text=f"P{index:02d} t={step}: activatie {p.activation:.3f} · vermoeidheid {p.fatigue:.3f} · herstel {p.recovery:.3f} · leeftijd {ind.life_course.age_years:.1f}",fill=FG)
        visible=list(self.sim.snapshots); end=next((n for n,s in enumerate(visible) if s is self._selected_snapshot()),len(visible)-1)
        series=visible[:end+1]; left,right,top,bottom=45,w-20,45,h-35
        c.create_rectangle(left,top,right,bottom,outline="#34445a")
        for field,color in (("activation","#60a5fa"),("fatigue","#fb7185"),("recovery","#34d399")):
            points=[]
            for n,snap in enumerate(series):
                value=getattr(snap[2][index].physiology,field)
                points.extend((left+(right-left)*n/max(1,len(series)-1),bottom-(bottom-top)*value))
            if len(points)>=4: c.create_line(*points,fill=color,width=2)
        c.create_text(left,bottom+16,anchor="w",text=f"t={series[0][0]} → t={step}  |  blauw activatie · rood vermoeidheid · groen herstel",fill=MUTED)
        self._apply_diagram_zoom(c)
        org=orgs[ind.affiliation]; members=[i for i in individuals if i.affiliation==ind.affiliation]
        group=group_summary(members,org); n=len(members); neff=effective_sample_size(n,.75)
        self._update_text(self.formal_text,[
            f"FORMEEL MODEL · P{index:02d} · {org.name} · t={step} / E{episode}",
            "(1) Observatie y = 0.5 stress + 0.3 activatie + 0.2 vermoeidheid",
            f"    y = {observation(ind):.4f}; synthetische proxy, geen meting of diagnose.",
            f"(2) Ruisobservatie={ind.assessment.observed:.4f}; interval [{ind.assessment.lower:.4f}, {ind.assessment.upper:.4f}]; modelcategorie={ind.assessment.category}.",
            "    De categorie gebruikt alleen de synthetische proxy; dit is geen gevalideerde inschatting of besluit.",
            "(3) Cognitie x: de simulator werkt opinie, vertrouwen en stress bij via sociale/institutionele input.",
            f"    opinie={ind.opinion:+.4f}, vertrouwen={ind.trust:.4f}, stress={ind.stress:.4f}",
            "(4) p(t+1) = Fp(t) + Gx(t) + Je(t): begrensd model met stress, sociaal verschil en schok.",
            f"    activatie={p.activation:.4f}, vermoeidheid={p.fatigue:.4f}, herstel={p.recovery:.4f}",
            f"    basis={p.baseline:.2f}, reactiviteit={p.reactivity:.2f}, regulatie={p.regulation:.2f}, slaapsteun={p.sleep_support:.2f}",
            f"Levensloop: {ind.life_course.age_years:.2f} synthetische jaren · {ind.life_course.stage}; één stap = één aangenomen dag.",
            f"Recursieve overtuiging (hypothese, diepte 2): {nested_belief_proxy(ind.opinion, group['mean_opinion'], 2):+.4f}; geen geobserveerde overtuiging.",
            "(6,9) Groep en organisatie: gemiddelde ledenopinie voedt beleidsupdate.",
            f"    q: opinie={group['mean_opinion']:+.4f}, stress={group['mean_stress']:.4f}, y={group['mean_observation']:.4f}; beleid={group['policy']:+.4f}",
            f"(7) Effectieve steekproef n/(1+(n−1)ρ): n={n}, voorbeeld ρ=0.75 → {neff:.3f} (aanname, geen gemeten correlatie).",
            "(5,8,10–12) Probabilistische taalproductie, normatieve kosten en interventies zijn niet empirisch geïmplementeerd.",
            "Alle waarden zijn illustratief en niet gevalideerd; geen gevolgtrekkingen over echte personen."])
        self._draw_spatial()

    def _build_dossier(self, parent):
        self.dossier_page = 0
        self.dossier_records = []
        self.dossier_org = tk.StringVar(value=ORG_NAMES[0])
        self.dossier_kind = tk.StringVar(value="Alles")
        self.dossier_member = tk.StringVar()
        self.dossier_query = tk.StringVar()
        bar = tk.Frame(parent, bg=PANEL); bar.pack(fill="x", padx=8, pady=4)
        tk.Button(bar, text="◀", command=lambda: self._dossier_change_org(-1)).pack(side="left")
        org = ttk.Combobox(bar, textvariable=self.dossier_org, values=ORG_NAMES, state="readonly", width=19)
        org.pack(side="left", padx=3); org.bind("<<ComboboxSelected>>", self._dossier_filter_changed)
        tk.Button(bar, text="▶", command=lambda: self._dossier_change_org(1)).pack(side="left")
        kind = ttk.Combobox(bar, textvariable=self.dossier_kind, state="readonly", width=20,
                            values=("Alles", "Intern gesprek", "Extern gesprek", "Terugkoppeling", "Organisatiebericht", "Modelinschatting"))
        kind.pack(side="left", padx=8); kind.bind("<<ComboboxSelected>>", self._dossier_filter_changed)
        tk.Label(bar, text="Persoon (P00)", bg=PANEL, fg=FG).pack(side="left")
        member = tk.Entry(bar, textvariable=self.dossier_member, width=7); member.pack(side="left", padx=4)
        tk.Label(bar, text="Zoeken", bg=PANEL, fg=FG).pack(side="left")
        query = tk.Entry(bar, textvariable=self.dossier_query, width=16); query.pack(side="left", padx=4)
        member.bind("<KeyRelease>", self._dossier_filter_changed); query.bind("<KeyRelease>", self._dossier_filter_changed)
        tk.Button(bar, text="CSV", command=self._export_dossier).pack(side="right")
        self.dossier_summary = tk.Label(parent, bg=PANEL, fg=MUTED, anchor="w")
        self.dossier_summary.pack(fill="x", padx=10)
        tk.Label(parent, bg=PANEL, fg=MUTED, anchor="w",
                 text="Groen: intern · blauw: extern · oranje: modelterugkoppeling · paars: organisatiebericht. Gesprekstekst is synthetisch.").pack(fill="x", padx=10)
        table = tk.Frame(parent, bg=PANEL); table.pack(fill="both", expand=True, padx=8, pady=4)
        self.dossier_tree = ttk.Treeview(table, columns=("time", "kind", "sender", "recipient", "topic", "message"), show="headings", selectmode="browse", height=6)
        for key, title, width in (("time", "Tijd / episode", 105), ("kind", "Soort", 120), ("sender", "Van", 100),
                                  ("recipient", "Aan", 110), ("topic", "Onderwerp", 135), ("message", "Inhoud", 400)):
            self.dossier_tree.heading(key, text=title); self.dossier_tree.column(key, width=width, minwidth=60)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.dossier_tree.yview)
        self.dossier_tree.configure(yscrollcommand=scroll.set); scroll.pack(side="right", fill="y")
        self.dossier_tree.pack(side="left", fill="both", expand=True)
        for tag, color in (("Intern gesprek", "#b4efcf"), ("Extern gesprek", "#b7d7ff"),
                           ("Terugkoppeling", "#ffd18a"), ("Organisatiebericht", "#d8c5ff"), ("Modelinschatting", "#ffe599")):
            self.dossier_tree.tag_configure(tag, foreground=color)
        self.dossier_tree.bind("<<TreeviewSelect>>", self._dossier_show_detail)
        self.dossier_tree.bind("<Double-1>", self._dossier_jump)
        pager = tk.Frame(parent, bg=PANEL); pager.pack(fill="x", padx=8)
        tk.Button(pager, text="◀ Vorige pagina", command=lambda: self._dossier_move_page(-1)).pack(side="left")
        self.dossier_page_label = tk.Label(pager, bg=PANEL, fg=FG); self.dossier_page_label.pack(side="left", padx=8)
        tk.Button(pager, text="Volgende pagina ▶", command=lambda: self._dossier_move_page(1)).pack(side="left")
        tk.Button(pager, text="Ga naar tijdstip", command=self._dossier_jump).pack(side="right")
        self.dossier_detail = tk.Text(parent, height=4, bg="#17263a", fg=FG, wrap="word", relief="flat")
        self.dossier_detail.pack(fill="x", padx=8, pady=5)

    def _dossier_filter_changed(self, _event=None):
        self.dossier_page = 0
        self._refresh_dossier()

    def _dossier_change_org(self, delta):
        self.dossier_org.set(ORG_NAMES[(ORG_NAMES.index(self.dossier_org.get()) + delta) % len(ORG_NAMES)])
        self._dossier_filter_changed()

    def _dossier_move_page(self, delta):
        self.dossier_page += delta
        self._refresh_dossier()

    def _refresh_dossier(self):
        if not hasattr(self, "dossier_tree"): return
        step, episode, individuals, organizations, _ = self._selected_snapshot()
        org_id = ORG_NAMES.index(self.dossier_org.get())
        records = self.sim.dossier_entries(org_id, step, episode, self.dossier_kind.get(),
                                           self.dossier_member.get(), self.dossier_query.get())
        self.dossier_records = records
        pages = max(1, (len(records) + 49) // 50)
        self.dossier_page = max(0, min(self.dossier_page, pages - 1))
        selected = self.dossier_tree.selection()
        selected_id = selected[0] if selected else None
        self.dossier_tree.delete(*self.dossier_tree.get_children())
        start = self.dossier_page * 50
        for index, entry in enumerate(records[start:start + 50], start):
            self.dossier_tree.insert("", "end", iid=str(index), tags=(entry.kind,),
                values=(f"{entry.step} / E{entry.episode}", entry.kind, entry.sender, entry.recipient, entry.topic, entry.message))
        if selected_id is not None and self.dossier_tree.exists(selected_id):
            self.dossier_tree.selection_set(selected_id)
        else:
            self._update_text(self.dossier_detail, ["Selecteer een regel voor inhoud en modelwaarden."])
        org = organizations[org_id]
        members = sum(i.affiliation == org_id for i in individuals)
        discarded = self.sim.dossier_discarded[org_id]
        self.dossier_summary.config(text=f"{org.name} · {members} leden · beleid {org.policy:+.3f} · legitimiteit {org.legitimacy:.3f} · "
            f"t={step}, E{episode} · {len(records)} resultaten · {discarded} oudere regels vervallen")
        self.dossier_page_label.config(text=f"Pagina {self.dossier_page + 1} / {pages} (chronologisch)")

    def _dossier_show_detail(self, _event=None):
        selection = self.dossier_tree.selection()
        if not selection: return
        idx = int(selection[0])
        if idx >= len(self.dossier_records): return
        entry = self.dossier_records[idx]
        self._update_text(self.dossier_detail, [f"{entry.sender} → {entry.recipient} · {entry.kind} · {entry.topic}",
                                                entry.message, "Modelinformatie: " + entry.evidence])

    def _dossier_jump(self, _event=None):
        selection = self.dossier_tree.selection()
        if not selection: return
        entry = self.dossier_records[int(selection[0])]
        for index, snap in enumerate(self.sim.snapshots):
            if (snap[0], snap[1]) == (entry.step, entry.episode):
                self.running = False; self.trace_index = index; self._refresh(); return
        self._update_text(self.dossier_detail, ["De snapshot van dit tijdstip is niet meer in de tracebackbuffer.", entry.message, entry.evidence])

    def _export_dossier(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="organisatiedossier.csv", filetypes=[("CSV", "*.csv")])
        if not path: return
        with open(path, "w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow(["stap", "episode", "soort", "afzender", "ontvanger", "onderwerp", "inhoud", "modelinformatie"])
            writer.writerows((e.step, e.episode, e.kind, e.sender, e.recipient, e.topic, e.message, e.evidence) for e in self.dossier_records)

    def _draw_network(self):
        c=self.network_canvas
        c.delete("all")
        w=max(400,c.winfo_width()); h=max(350,c.winfo_height())
        cx,cy=w/2,h/2
        snap=self._selected_snapshot()
        individuals,organizations=snap[2],snap[3]
        orgpos=[]
        for j in range(7):
            a=2*math.pi*j/7-math.pi/2
            orgpos.append((cx+min(w*.33,280)*math.cos(a),cy+min(h*.32,190)*math.sin(a)))
        pos=[]
        for i in individuals:
            a=2*math.pi*(i.id//7)/6.0 + i.affiliation*.7
            ox,oy=orgpos[i.affiliation]
            pos.append((ox+35*math.cos(a),oy+35*math.sin(a)))
        for a,b in self.sim.edges:
            x1,y1=pos[a];x2,y2=pos[b]
            c.create_line(x1,y1,x2,y2,fill="#283b53",width=1)
        for i,(x,y) in zip(individuals,pos):
            r=4+2*i.trust
            color=ORG_COLORS[i.affiliation]
            tag=f"person_{i.id}"
            c.create_oval(x-r,y-r,x+r,y+r,fill=color,outline="",activeoutline="white",activewidth=2,tags=(tag,))
            c.tag_bind(tag,"<Button-1>",lambda e,index=i.id:self._open_individual(index))
        for o,(x,y) in zip(organizations,orgpos):
            tag=f"org_{o.id}"
            c.create_oval(x-19,y-19,x+19,y+19,fill=ORG_COLORS[o.id],outline="#ffffff",width=1,tags=(tag,))
            c.create_text(x,y,text=str(o.id+1),fill="#09111f",font=("Segoe UI",11,"bold"),tags=(tag,))
            c.tag_bind(tag,"<Button-1>",lambda e,index=o.id:self._open_organization(index))
            c.create_text(x,y+31,text=f"{o.name}  {o.policy:+.2f}",fill=FG,font=("Segoe UI",9))
        c.create_text(16,18,anchor="w",text="● ORGANISATIES (GROOT)  ·  INDIVIDUEN (KLEIN)  ·  VERBINDINGEN (LIJNEN)",fill=MUTED,font=("Segoe UI",9))
        c.create_text(16,h-18,anchor="w",text="Klik een knoop · wiel: zoom · rechts/midden slepen: verplaats · kleur: organisatie",fill=MUTED,font=("Segoe UI",9))
        self._apply_diagram_zoom(c)

    def _refresh_relation_choices(self, individuals=None, organizations=None):
        if individuals is None:
            snap=self._selected_snapshot(); individuals,organizations=snap[2],snap[3]
        people=[f"P{i.id:02d}" for i in individuals]
        orgs=[f"O{o.id}: {o.name}" for o in organizations] if self.show_org_var.get() else []
        values=people+orgs
        self.rel_a_combo["values"]=values; self.rel_b_combo["values"]=values
        if self.rel_a.get() not in values: self.rel_a.set(values[0] if values else "")
        if self.rel_b.get() not in values or self.rel_b.get()==self.rel_a.get(): self.rel_b.set(values[1] if len(values)>1 else "")
        self._draw_relationships()

    def _selected_snapshot(self):
        idx=getattr(self, "trace_index", -1)
        if idx < 0: idx=len(self.sim.snapshots)-1
        idx=max(0,min(len(self.sim.snapshots)-1,idx))
        return self.sim.snapshots[idx]

    def _entity_at(self, label, individuals, organizations):
        if label.startswith("P"):
            return next((i for i in individuals if f"P{i.id:02d}"==label),None), "individual"
        try: return organizations[int(label[1:].split(":")[0])], "organization"
        except (ValueError,IndexError): return None, "organization"

    def _draw_relationships(self):
        if not hasattr(self,"relationship_canvas") or not self.sim.snapshots:return
        c=self.relationship_canvas; c.delete("all"); w=max(600,c.winfo_width()); h=max(400,c.winfo_height())
        a_label,b_label=self.rel_a.get(),self.rel_b.get()
        points=[]
        for step,episode,inds,orgs,_ in self.sim.snapshots:
            a,ak=self._entity_at(a_label,inds,orgs); b,bk=self._entity_at(b_label,inds,orgs)
            if not a or not b: continue
            av=a.opinion if ak=="individual" else a.policy; bv=b.opinion if bk=="individual" else b.policy
            opinion=abs(av-bv)/2
            at=a.trust if ak=="individual" else a.legitimacy; bt=b.trust if bk=="individual" else b.legitimacy
            trust=abs(at-bt)
            ar=a.resources; br=b.resources
            resources=abs(ar-br)
            distance=.55*opinion+.25*trust+.20*resources
            points.append((step,distance,opinion,trust,resources))
        if not points:return
        c.create_text(18,18,anchor="w",text=f"BILATERALE DIVERGENTIE  {a_label} ↔ {b_label}",fill=FG,font=("Segoe UI",12,"bold"))
        x0,y0=60,55; pw,ph=w-110,h-130; c.create_rectangle(x0,y0,x0+pw,y0+ph,outline="#34445a")
        mx=max(.05,max(p[1] for p in points)); line=[]
        for j,p in enumerate(points): line += [x0+j/max(1,len(points)-1)*pw,y0+ph-p[1]/mx*ph]
        if len(line)>=4:c.create_line(*line,fill="#fb7185",width=3)
        current=points[-1]; c.create_text(x0,y0+ph+20,anchor="w",text=f"t={points[0][0]}",fill=MUTED)
        c.create_text(x0+pw,y0+ph+20,anchor="e",text=f"t={points[-1][0]}",fill=MUTED)
        c.create_text(x0,y0+ph+48,anchor="w",text=f"afstand={current[1]:.3f}  opinie={current[2]:.3f}  vertrouwen/legitimiteit={current[3]:.3f}  middelen={current[4]:.3f}",fill=FG,font=("Consolas",10))
        c.create_text(x0,y0+ph+72,anchor="w",text="Attributie: 55% opinie · 25% vertrouwen/legitimiteit · 20% middelen",fill=MUTED,font=("Segoe UI",9))
        self._apply_diagram_zoom(c)

    def _draw_individuals(self, individuals, step):
        c=self.individual_canvas; c.delete("all")
        w=max(450,c.winfo_width())
        c.create_text(18,18,anchor="w",text=f"INDIVIDUEN  ·  toestand op t={step}",fill=FG,font=("Segoe UI",12,"bold"))
        barw=max(180,(w-220)//2)
        for n,i in enumerate(individuals):
            col=n%2; row=n//2; x=25+col*(barw+80); y=48+row*43
            c.create_text(x,y,anchor="w",text=f"P{i.id:02d}  {ORG_NAMES[i.affiliation]}",fill=FG,font=("Consolas",9))
            c.create_rectangle(x+barw-100,y-8,x+barw,y+2,outline="#34445a")
            c.create_rectangle(x+barw-100,y-8,x+barw-100+(i.opinion+1)/2*100,y+2,fill=ORG_COLORS[i.affiliation],outline="")
            c.create_text(x+barw+8,y-3,anchor="w",text=f"opinie {i.opinion:+.2f} stress {i.stress:.2f} trust {i.trust:.2f}",fill=MUTED,font=("Consolas",8))

    def _refresh_individual_dashboard(self):
        if not hasattr(self, "individual_list") or not self.individual_list.curselection(): return
        idx=self.individual_list.curselection()[0]
        snap=self._selected_snapshot()
        step,_,individuals,_,_=snap
        if idx >= len(individuals): return
        i=individuals[idx]; c=self.individual_canvas; c.delete("all")
        c.create_text(28,28,anchor="w",text=f"DASHBOARD P{i.id:02d} · {ORG_NAMES[i.affiliation]} · t={step}",fill=FG,font=("Segoe UI",14,"bold"))
        rows=[("Opinie",i.opinion,-1,1),("Vertrouwen",i.trust,0,1),("Stress",i.stress,0,1),("Middelen",i.resources,0,1),("Vatbaarheid",i.susceptibility,0,1)]
        for n,(label,value,lo,hi) in enumerate(rows):
            y=78+n*42; c.create_text(30,y,anchor="w",text=label,fill=MUTED,font=("Segoe UI",10)); c.create_rectangle(150,y-8,470,y+8,outline="#34445a"); c.create_rectangle(150,y-8,150+320*(value-lo)/(hi-lo),y+8,fill=ORG_COLORS[i.affiliation],outline=""); c.create_text(480,y,anchor="w",text=f"{value:+.3f}" if lo<0 else f"{value:.3f}",fill=FG,font=("Consolas",10))
        c.create_text(30,310,anchor="w",text="Communicatie van deze persoon",fill=FG,font=("Segoe UI",11,"bold"))
        logs=[x for x in self.sim.communication_log if x[0] <= step and x[2] == f"P{i.id:02d}"][-8:]
        for n,(_,_,src,dst,topic,message) in enumerate(logs):
            c.create_text(30,340+n*34,anchor="w",text=f"→ {dst} · {topic}: {message}",fill="#b9d6f0",font=("Consolas",8),width=max(400,c.winfo_width()-60))
        self._apply_diagram_zoom(c)

    def _draw_organizations(self, organizations, step):
        c=self.organization_canvas; c.delete("all")
        w=max(450,c.winfo_width())
        c.create_text(18,18,anchor="w",text=f"ORGANISATIES  ·  toestand op t={step}",fill=FG,font=("Segoe UI",12,"bold"))
        for n,o in enumerate(organizations):
            y=58+n*52; c.create_oval(24,y-12,48,y+12,fill=ORG_COLORS[o.id],outline="")
            c.create_text(60,y,anchor="w",text=o.name,fill=FG,font=("Segoe UI",10,"bold"))
            values=[("beleid",o.policy,-1,1),("legitimiteit",o.legitimacy,0,1),("middelen",o.resources,0,1),("responsiviteit",o.responsiveness,0,1)]
            for j,(label,value,lo,hi) in enumerate(values):
                x=220+j*max(115,(w-250)//4)
                c.create_text(x,y-10,anchor="w",text=label,fill=MUTED,font=("Consolas",8))
                c.create_rectangle(x,y+1,x+90,y+9,outline="#34445a")
                c.create_rectangle(x,y+1,x+90*(value-lo)/(hi-lo),y+9,fill=ORG_COLORS[o.id],outline="")
                c.create_text(x+94,y+5,anchor="w",text=f"{value:.2f}",fill=FG,font=("Consolas",8))
        self._apply_diagram_zoom(c)

    def _draw_metrics(self, history=None, selected_step=0):
        c=self.metric_canvas;c.delete("all")
        w=max(450,c.winfo_width());h=max(340,c.winfo_height())
        hist=list(self.sim.history if history is None else history)
        if not hist:return
        panels=[("GEMIDDELDE OPINIE",1,-1,1,"#60a5fa"),("SPREIDING σ",2,0,1,"#34d399"),("MAX. TOESTANDSVERANDERING Δ",3,0,max(.05,max(x[3] for x in hist)),"#fb7185"),("BELEIDSAFSTAND",4,0,2,"#fbbf24")]
        for p,(name,index,lo,hi,color) in enumerate(panels):
            col=p%2;row=p//2
            x0=45+col*w/2;y0=45+row*h/2
            pw=w/2-75;ph=h/2-85
            c.create_text(x0,y0-20,text=name,anchor="w",fill=FG,font=("Segoe UI",10,"bold"))
            c.create_rectangle(x0,y0,x0+pw,y0+ph,outline="#34445a")
            if len(hist)>1:
                pts=[]
                for j,v in enumerate(hist):
                    pts.extend((x0+j/(len(hist)-1)*pw,y0+ph-(v[index]-lo)/(hi-lo)*ph))
                c.create_line(*pts,fill=color,width=2,smooth=False)
            c.create_text(x0+pw,y0+ph+15,text=f"laatste: {hist[-1][index]:.5f}",anchor="e",fill=MUTED,font=("Consolas",9))
            c.create_text(x0,y0+ph+15,text=f"t={hist[0][0]}",anchor="w",fill=MUTED,font=("Consolas",8))
            if len(hist)>1:
                selected=max(hist[0][0],min(selected_step,hist[-1][0]))
                xpos=x0+(selected-hist[0][0])/(hist[-1][0]-hist[0][0])*pw
                c.create_line(xpos,y0,xpos,y0+ph,fill="#dbeafe",dash=(3,3))
            c.create_text(x0+pw/2,y0+ph+15,text=f"t={hist[-1][0]}",anchor="center",fill=MUTED,font=("Consolas",8))
        self._apply_diagram_zoom(c)

    def export_csv(self):
        path=filedialog.asksaveasfilename(defaultextension=".csv",initialfile="society_metrics.csv",filetypes=[("CSV","*.csv")])
        if not path:return
        with open(path,"w",newline="",encoding="utf-8") as f:
            writer=csv.writer(f);writer.writerow(["step","mean_opinion","opinion_stddev","max_delta","policy_gap"])
            writer.writerows(self.sim.history)
        self.sim._event("EXPORT",f"Metrieken opgeslagen: {path}")
    def export_log(self):
        path=filedialog.asksaveasfilename(defaultextension=".txt",initialfile="society_log.txt",filetypes=[("Text","*.txt")])
        if not path:return
        with open(path,"w",encoding="utf-8") as f:
            for step,ep,kind,msg in self.sim.log:
                f.write(f"[{step:06d} / E{ep:03d}] {kind:8} {msg}\n")
        self.sim._event("EXPORT",f"Log opgeslagen: {path}")

if __name__ == "__main__":
    SimulatorApp().mainloop()
