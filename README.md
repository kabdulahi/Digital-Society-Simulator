# Digital Society Simulator

Digital Society Simulator is a Python desktop application for exploring a synthetic society of 37 individuals and seven organizations. It combines a bounded opinion-dynamics model, institutional feedback, generated Dutch communication, visualizations, and chronological organization dossiers.

The application is an exploratory simulation. Its agents, communications, parameters, and outcomes are synthetic; they are not observations of real people or institutions. Its model is inspired by *A Formal Grammar of Standard Dutch: Recursive Cognition, Physiology, Institutional Cybernetics, and a Fictional Life Course*, but does not implement the complete paper or establish its scientific claims.

**Copyright © 2026 RVSHR B.V. (i.o.).**  
Website: [karim.1e100.nl](https://karim.1e100.nl)

## Requirements and startup

- Python 3.9 or newer with the standard library and Tkinter available.
- A graphical desktop session. Tkinter must be able to open a window; on Linux/WSL this may require an available display server and a separately installed Tk package.
- No third-party Python packages or network access are required at runtime.

From the project directory:

```sh
python simulator.py
```

On systems where Python 3 is invoked as `python3`, use `python3 simulator.py`. To check Tkinter independently, run `python -m tkinter`; it should open a small test window.

## Project structure

```text
simulator.py                   Model, Dutch-language generator, and Tkinter UI
language/
  communicatie.json            Topics and sentence fragments used by the generator
  lexicon.json                 Pronouns and additional lexical data
  grammar.json                 Legacy templates and grammatical word lists
  morphology.json              Descriptive morphology data
  semantics.json               Semantic domain and role vocabulary
  discourse.json               Discourse-relation word lists
  test_sentences.json          Example positive and negative sentences
  README.md                    Notes on the language data
test_dossiers.py               Dossier filtering, chronology, and retention tests
test_language.py               Language-generation and integration tests
```

Language files are loaded relative to `simulator.py`, not the current working directory. `_language_data()` falls back to the supplied default when a file is missing or contains invalid JSON. In particular, missing or incomplete `communicatie.json` causes the sentence generator to use a short fallback sentence. Existing JSON files are not all fully executable grammar specifications: see [Dutch communication](#dutch-communication).

## Core architecture

The application uses only the Python standard library:

- `Settings` holds the mutable simulation parameters and seed.
- `Individual` holds an ID, organization affiliation, opinion, trust, stress, resources, susceptibility, and neighbor IDs.
- `Organization` holds an ID, name, policy, legitimacy, resources, and responsiveness.
- `Society` owns the agents, network, random generator, step logic, snapshots, metrics, event logs, and dossiers.
- `DossierEntry` records a timestamped synthetic communication or feedback item and its associated model information.
- `DutchGrammar` loads language data, composes controlled Dutch text, and performs limited keyword analysis.
- `SimulatorApp` builds the Tkinter interface, runs scheduled simulation ticks, and renders the views.

Agents are assigned to organizations by `id % 7`. At initialization, the network is constructed from weighted random choices favoring neighbors in the same organization. Connections are undirected, deduplicated, and remain fixed during a run. The default simulation seed is `20261109`.

## Simulation model

Each call to `Society.step()` advances the global and episode step counters. Individuals' opinions are updated from a copy of the previous opinions and organizational policies. An individual's target combines its prior opinion, the mean opinion of its neighbors, and the policy of its affiliated organization, weighted by trust and institutional legitimacy. Relaxation, susceptibility, and communication scale the movement toward that target. The update additionally includes:

- A divergence term proportional to `controversy × polarization × (individual opinion − neighbor mean)`.
- Gaussian noise, optionally reduced as the episode progresses.
- An occasional common external shock controlled by shock probability and strength.

Opinions are clamped to `[-1, 1]`. After individual opinions are calculated, each organization's policy target combines the new mean opinion of its members, the previous policies of the other organizations, and its own previous policy. Coordination and institutional alignment determine the mixture; relaxation, responsiveness, resources, communication, and the shock determine the update. Policies are also clamped to `[-1, 1]`.

Trust moves gradually toward agreement with the updated policy. Stress responds to individual opinion movement and decays gradually. Individual resources and susceptibility, and organization legitimacy and responsiveness, are initialized but do not evolve in ordinary steps; organization resources can change at an episode boundary.

The model is an intentionally simplified construction. In particular, generated communication text does not feed back into the numerical update. The two displayed neighbor contacts per individual are selected from its neighbors by opinion difference; the numerical social influence uses the mean of **all** neighbors, not a separately calculated effect for each displayed contact.

### Metrics and episodes

The metrics history stores global step, mean individual opinion, opinion standard deviation, maximum absolute change in individual opinion or organization policy, and the range of organization policies. A step counts toward stability when the maximum change is below `tolerance` and there is no shock. An episode converges after `stable_window` consecutive stable steps, or reaches a timeout at `max_steps`.

An episode transition resets the episode step and metrics history and perturbs selected individual and organization fields. The global step continues. With automatic episodes enabled, the UI starts a new episode after convergence or timeout.

## Controls and parameter search

The left control panel provides start, pause, reset, single-step and new-episode actions. Its sliders adjust social and institutional influence, inter-organizational coordination, communication, noise, shock probability and strength, trust adaptation, relaxation, convergence tolerance, stability window, controversy, polarization, and institutional alignment. The UI normalizes social and institutional influence when their sum exceeds one.

`Stabiel` and `Chaos` set example parameter combinations. They are presets, not guarantees of convergence or mathematical chaos. Desired mean opinion, spread, and policy gap can also be set before selecting **Optimaliseer parameters**.

The optimizer is a small bounded random coordinate search. It creates fresh `Society` instances, runs each candidate for 28 steps, and scores the absolute differences between the desired and resulting mean opinion, spread, and policy gap. It tries 24 candidate changes across five parameters. Candidates use varying seeds, so scores reflect both parameter and initialization differences; it does not optimize from the currently displayed snapshot or guarantee a global optimum. This is a heuristic rather than a statistical or causal estimator.

## Views, traceback, and logs

- **Netwerk** draws organizations, individual nodes, and social connections.
- **Metrieken** draws the four metrics for the selected snapshot's retained episode history.
- **Toestanden** lists individual and organization fields.
- **Individuen** selects a person and shows selected state values and recent outgoing generated messages.
- **Organisaties** displays organization state values.
- **Organisatiedossiers** browses entries by organization, type, person, and text. Entries distinguish internal and external generated conversations, policy feedback, and organization summaries. Select a row for its message and model information; double-click it or use **Ga naar tijdstip** to select a retained snapshot. The CSV button exports the filtered results, not only the current page.
- **Primitieven & logs** displays a compact set of metrics and log counts.
- **Bilaterale relaties** compares two selected entities with a weighted descriptive distance: `0.55 × |opinion/policy difference| / 2 + 0.25 × |trust/legitimacy difference| + 0.20 × |resource difference|`. These weights are visualization choices, not estimates of causal influence. The current implementation plots all retained snapshots and displays the latest plotted point, even when an earlier traceback snapshot is selected.

The lower notebook contains the event log, thresholded state transitions, generated communication log, and anomaly list. Anomalies are rule-based flags for a large maximum change, high opinion spread, high policy gap, or a rapid increase or decrease in spread. They are descriptive alerts, not diagnostic or statistical conclusions.

The shared **TRACEBACK** slider and arrow buttons select retained snapshots and pause the run. A snapshot contains deep copies of individuals and organizations and a copy of the then-current metrics history. Traceback is for inspection; resuming does not restore the simulation or random-generator state to the selected snapshot. Different views have different retention and filtering behavior: the dossier filters by selected step and episode, while the general event and anomaly panes show recent retained entries, and the bilateral graph uses the full retained snapshot buffer.

### In-memory retention and exports

Data is held in bounded in-memory buffers; oldest entries are discarded when a buffer is full. Reset creates a new society, and exiting the application discards the in-memory run.

| Buffer | Maximum entries |
| --- | ---: |
| Metric history | 350 |
| Snapshots | 1,200 |
| State transitions | 400 |
| General communication log | 1,800 |
| Organization dossier | 5,000 per organization |
| Anomalies | 1,200 |
| Event log | 1,200 |

The dossier displays the number of entries discarded for the selected organization. Dossier entries and snapshots have independent retention; a dossier entry can remain after its corresponding snapshot has expired. The control panel exports the retained **current episode** metrics to CSV and the retained general event log to text. The dossier CSV export uses UTF-8 with a byte-order mark and includes each entry's model-information field.

## Dutch communication

`language/communicatie.json` supplies topics, subordinate clauses, responses, agreement/disagreement follow-ups, transitions, and reflections. `DutchGrammar.sentence()` combines them into three-sentence synthetic messages. A local random generator is seeded from the step, sender, recipient, and state values; text generation does not consume the simulation's random stream. The choice between agreement and disagreement follow-ups uses the simulated opinion difference. Topics are generated choices, not measured facts.

`DutchGrammar.parse()` and `analyze()` provide shallow token and keyword checks. They do not build a full parse tree, validate grammaticality, infer complete semantic roles, or assess CEFR level. The other JSON files contain vocabulary, descriptive features, or legacy templates; loading a file does not mean all its fields affect generation. `test_sentences.json` is example data, not an automatically executed grammar-validation corpus. See [language/README.md](language/README.md) for the data format and extension notes.

## Running tests

Run the included model, language, and dossier tests without generating bytecode files:

```sh
python -B -m unittest -v test_language test_dossiers
```

These tests cover reproducible language generation, message variety for a fixed pair, opinion-gap wording, dossier membership, episode filtering, and bounded retention. They do not establish linguistic correctness across all generated combinations, validate the model scientifically, or replace manual GUI testing.

## Research context and limitations

The simulator borrows concepts such as feedback, institutional coordination, controlled Dutch text, and multiple levels of state from the referenced working paper. It does not implement a complete Dutch grammar, a physiological model, a life-course model, an empirical institutional classification pipeline, or the paper's full formal apparatus. Simulation output should be interpreted as the behavior of these particular programmed rules, not as evidence about actual individuals, organizations, clinical conditions, or causal responsibility.

The repository does not currently include a separate license file. The copyright notice above does not by itself grant an open-source license.
