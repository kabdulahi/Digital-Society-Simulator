#!/usr/bin/env python3
"""Digital Society Simulator: synthetic multi-agent cybernetics (stdlib only)."""
from __future__ import annotations
import csv
import copy
import math
import random
import tkinter as tk
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import ttk, filedialog

ORG_NAMES = ["Onderwijs", "Gezondheidszorg", "Bestuur", "Media", "Economie", "Onderzoek", "Gemeenschapsraad"]
ORG_COLORS = ["#f59e0b", "#06b6d4", "#a78bfa", "#fb7185", "#34d399", "#60a5fa", "#eab308"]
BG, PANEL, FG, MUTED, ACCENT = "#0b1220", "#111c2d", "#e5eefb", "#9aafc7", "#60a5fa"


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


@dataclass
class Organization:
    id: int
    name: str
    policy: float
    legitimacy: float
    resources: float
    responsiveness: float


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
        self.snapshots = deque(maxlen=350)
        self.transitions = deque(maxlen=400)
        self.communication_log = deque(maxlen=1800)
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

    def _create(self):
        r = self.rng
        self.organizations = [Organization(i, name, r.uniform(-.65, .65), r.uniform(.45, .9),
                                           r.uniform(.35, .95), r.uniform(.45, .9)) for i, name in enumerate(ORG_NAMES)]
        self.individuals = [Individual(i, i % 7, r.uniform(-.9, .9), r.uniform(.3, .9),
                                        r.uniform(.1, .55), r.uniform(.2, .95), r.uniform(.35, .95)) for i in range(37)]
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
            change = c.relaxation * i.susceptibility * (0.25 + 0.75*c.communication) * (target - old[i.id])
            change += shock * (0.25 + 0.3*i.susceptibility) + r.gauss(0, temp)*.10
            new_op.append(clamp(old[i.id] + change))
            for neighbor in sorted(i.neighbors, key=lambda j: abs(old[j] - old[i.id]), reverse=True)[:2]:
                direction = "eensgezind" if abs(old[neighbor] - old[i.id]) < .15 else "verschillend"
                self.communication_log.append((self.global_step, self.episode, f"P{i.id:02d}", f"P{neighbor:02d}",
                    "opinie en vertrouwen", f"Mijn standpunt is {old[i.id]:+.2f}; jouw standpunt is {old[neighbor]:+.2f} ({direction})."))
        new_p = []
        for org in self.organizations:
            members = [new_op[i.id] for i in self.individuals if i.affiliation == org.id]
            local = sum(members)/len(members)
            other = sum(oldp[j] for j in range(7) if j != org.id)/6
            target = (1-c.coordination)*local + c.coordination*other
            new_p.append(clamp(oldp[org.id] + c.relaxation*org.responsiveness*(0.25+0.75*c.communication)*org.resources*(target-oldp[org.id]) + shock*.18))
        delta = max([abs(a-b) for a,b in zip(new_op, old)] + [abs(a-b) for a,b in zip(new_p, oldp)])
        for i, v in zip(self.individuals, new_op):
            prior = i.opinion
            i.opinion = v
            agreement = 1-abs(v-new_p[i.affiliation])/2
            i.trust = max(0, min(1, i.trust + c.trust_adaptation*.03*(agreement-i.trust)))
            i.stress = max(0, min(1, i.stress + .02*(abs(v-prior)*3-i.stress*.18)))
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
        vals = new_op + new_p
        mean = sum(new_op)/37
        spread = math.sqrt(sum((v-mean)**2 for v in new_op)/37)
        policy_gap = max(new_p)-min(new_p)
        self.history.append((self.global_step, mean, spread, delta, policy_gap))
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
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("TNotebook", background=BG)
        style.configure("TNotebook.Tab", padding=(14,8))
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=25)
        style.configure("Treeview.Heading", background="#203047", foreground=FG)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.rowconfigure(1, weight=1)
        head = tk.Frame(self, bg=BG)
        head.grid(row=0,column=0,columnspan=2,sticky="ew",padx=14,pady=12)
        tk.Label(head,text="DIGITAL SOCIETY  /  CYBERNETIC LAB",fg=FG,bg=BG,font=("Segoe UI",18,"bold")).pack(side="left")
        self.status = tk.Label(head,text="GEREED",fg="#34d399",bg=BG,font=("Consolas",11,"bold"))
        self.status.pack(side="right")
        left = tk.Frame(self,bg=BG)
        left.grid(row=1,column=0,sticky="nsew",padx=(14,6),pady=(0,14))
        left.rowconfigure(0,weight=3)
        left.rowconfigure(1,weight=2)
        left.rowconfigure(2,weight=0)
        left.columnconfigure(0,weight=1)
        top = ttk.Notebook(left)
        top.grid(row=0,column=0,sticky="nsew")
        network = tk.Frame(top,bg=PANEL)
        metrics = tk.Frame(top,bg=PANEL)
        states = tk.Frame(top,bg=PANEL)
        individuals_view = tk.Frame(top,bg=PANEL)
        organizations_view = tk.Frame(top,bg=PANEL)
        top.add(network,text="  NETWERK  ")
        top.add(metrics,text="  METRIEKEN  ")
        top.add(states,text="  TOESTANDEN  ")
        top.add(individuals_view,text="  INDIVIDUEN  ")
        top.add(organizations_view,text="  ORGANISATIES  ")
        self.network_canvas = tk.Canvas(network,bg=PANEL,highlightthickness=0)
        self.network_canvas.pack(fill="both",expand=True)
        self.metric_canvas = tk.Canvas(metrics,bg=PANEL,highlightthickness=0)
        self.metric_canvas.pack(fill="both",expand=True)
        self.individual_canvas = tk.Canvas(individuals_view,bg=PANEL,highlightthickness=0)
        self.individual_canvas.pack(fill="both",expand=True)
        self.organization_canvas = tk.Canvas(organizations_view,bg=PANEL,highlightthickness=0)
        self.organization_canvas.pack(fill="both",expand=True)
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
        bottom.add(logframe,text="  LIVE LOGTAIL  ")
        bottom.add(transframe,text="  STATE TRANSITIONS  ")
        bottom.add(commframe,text="  COMMUNICATIELOG  ")
        self.logbox=tk.Text(logframe,bg=PANEL,fg="#b9d6f0",font=("Consolas",10),wrap="none",relief="flat")
        self.logbox.pack(fill="both",expand=True)
        self.transbox=tk.Text(transframe,bg=PANEL,fg="#b9d6f0",font=("Consolas",10),wrap="none",relief="flat")
        self.transbox.pack(fill="both",expand=True)
        self.comm_box=tk.Text(commframe,bg=PANEL,fg="#b9d6f0",font=("Consolas",9),wrap="none",relief="flat")
        self.comm_box.pack(fill="both",expand=True)
        self._build_trace_footer(left)
        right=tk.Frame(self,bg=PANEL,width=335)
        right.grid(row=1,column=1,sticky="ns",padx=(6,14),pady=(0,14))
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
        self._slider(controls,"social_influence","Sociale beïnvloeding",0,.75,.25)
        self._slider(controls,"institutional_influence","Institutionele invloed",0,.75,.18)
        self._slider(controls,"coordination","Interorganisationele coördinatie",0,1,.2)
        self._slider(controls,"communication","Communicatiesnelheid",.05,1,.5)
        self._slider(controls,"noise","Willekeurige ruis",0,.5,.08)
        self._slider(controls,"shock_probability","Schokkans per stap",0,.25,.035)
        self._slider(controls,"shock_strength","Sterkte van verstoringen",0,.9,.35)
        self._slider(controls,"trust_adaptation","Vertrouwensadaptatie",0,.5,.08)
        self._slider(controls,"relaxation","Aanpassingssnelheid",.01,.8,.14)
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

    def _tick(self):
        if self.running:
            self._apply()
            for _ in range(self.speed_var.get()):
                finished=self.sim.step()
                if finished:
                    if self.auto_episodes.get():
                        self.sim.new_episode()
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
        self._draw_network()
        self._draw_metrics(history, step)
        self._draw_individuals(individuals, step)
        self._draw_organizations(organizations, step)
        self.state_tree.delete(*self.state_tree.get_children())
        for i in individuals:
            self.state_tree.insert("", "end", values=(f"P{i.id:02d}",ORG_NAMES[i.affiliation],f"{i.opinion:+.3f}",f"{i.trust:.3f}",f"{i.stress:.3f}",f"{i.resources:.3f}"))
        for o in organizations:
            self.state_tree.insert("", "end",values=(f"O{o.id}",o.name,f"{o.policy:+.3f}",f"{o.legitimacy:.3f}","—",f"{o.resources:.3f}"))
        self._update_text(self.logbox,[f"[{step:06d} / E{ep:03d}] {kind:8} {msg}" for step,ep,kind,msg in list(s.log)[-220:]])
        self._update_text(self.transbox,[f"[{step:06d}] {who:22} {old:+.4f} → {new:+.4f}  (Δ {new-old:+.4f})" for step,who,old,new in list(s.transitions)[-250:]])

        comms=[x for x in s.communication_log if x[0] <= step][-180:]
        self._update_text(self.comm_box,[f"[{st:06d}/E{ep:03d}] {src:18} -> {dst:18} | {topic}: {message}" for st,ep,src,dst,topic,message in comms])

    def _update_text(self,widget,lines):
        widget.configure(state="normal")
        widget.delete("1.0","end")
        widget.insert("end","\n".join(lines))
        widget.see("end")
        widget.configure(state="disabled")

    def _draw_network(self):
        c=self.network_canvas
        c.delete("all")
        w=max(400,c.winfo_width()); h=max(350,c.winfo_height())
        cx,cy=w/2,h/2
        snap=self.sim.snapshots[max(0,min(len(self.sim.snapshots)-1,getattr(self,"trace_index",len(self.sim.snapshots)-1)))]
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
            c.create_oval(x-r,y-r,x+r,y+r,fill=color,outline="")
        for o,(x,y) in zip(organizations,orgpos):
            c.create_oval(x-19,y-19,x+19,y+19,fill=ORG_COLORS[o.id],outline="#ffffff",width=1)
            c.create_text(x,y,text=str(o.id+1),fill="#09111f",font=("Segoe UI",11,"bold"))
            c.create_text(x,y+31,text=f"{o.name}  {o.policy:+.2f}",fill=FG,font=("Segoe UI",9))
        c.create_text(16,18,anchor="w",text="● ORGANISATIES (GROOT)  ·  INDIVIDUEN (KLEIN)  ·  VERBINDINGEN (LIJNEN)",fill=MUTED,font=("Segoe UI",9))
        c.create_text(16,h-18,anchor="w",text="Kleur = organisatie; getal bij organisatie = beleidstoestand; alle verbindingen blijven binnen de gemeenschap.",fill=MUTED,font=("Segoe UI",9))

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
