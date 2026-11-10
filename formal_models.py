"""Inspectable, non-clinical toy instantiations of the paper's state equations."""
from dataclasses import dataclass


def bound(value, low=0.0, high=1.0):
    return max(low, min(high, value))


@dataclass
class Physiology:
    # Dimensionless simulated states, deliberately not physiological measurements.
    activation: float = 0.35
    fatigue: float = 0.25
    recovery: float = 0.70
    baseline: float = 0.30
    reactivity: float = 0.50
    regulation: float = 0.50
    sleep_support: float = 0.70
    observation_uncertainty: float = 0.05


@dataclass(frozen=True)
class SyntheticAssessment:
    """A model output with an uncertainty interval, not a diagnosis."""
    step: int
    observed: float
    lower: float
    upper: float
    category: str


@dataclass
class LifeCourse:
    """Synthetic elapsed age, with one simulation step interpreted as one day."""
    age_years: float = 0.0
    years_per_step: float = 1 / 365.25

    @property
    def stage(self):
        if self.age_years < 2: return "vroege kindertijd"
        if self.age_years < 6: return "kindertijd"
        if self.age_years < 12: return "schoolleeftijd"
        if self.age_years < 18: return "adolescentie"
        return "volwassenheid"

    def advance(self):
        self.age_years += self.years_per_step


def nested_belief_proxy(own_opinion, other_opinion, depth):
    """An explicit hypothetical recursion; not an inference of real beliefs."""
    if not 0 <= depth <= 8: raise ValueError("depth must be between 0 and 8")
    value = other_opinion
    for _ in range(depth):
        value = 0.5 * own_opinion + 0.5 * value
    return value


def physiology_step(p, stress, social_difference, shock):
    """Bounded model of p(t+1)=F p(t)+G x(t)+J e(t), with x=stress.

    These coefficients are illustrative, not calibrated or medical quantities.
    The returned object is new so previous snapshots remain stable.
    """
    activation = bound(p.activation + 0.12 * (p.baseline - p.activation)
                       + 0.08 * p.reactivity * stress + 0.04 * social_difference
                       + 0.10 * abs(shock) - 0.04 * p.regulation * p.recovery)
    fatigue = bound(p.fatigue + 0.025 * activation - 0.035 * p.sleep_support * p.recovery)
    recovery = bound(p.recovery + 0.04 * p.sleep_support * (1 - p.recovery)
                     - 0.025 * activation - 0.01 * fatigue)
    return Physiology(activation, fatigue, recovery, p.baseline, p.reactivity,
                      p.regulation, p.sleep_support, p.observation_uncertainty)


def observation(individual):
    """Synthetic, transparent measurement proxy y=H(x,p,c), without noise."""
    p = individual.physiology
    return bound(0.5 * individual.stress + 0.3 * p.activation + 0.2 * p.fatigue)


def synthetic_assessment(individual, step, error_fraction):
    """Simulate a bounded observation and label only when its interval is unambiguous.

    error_fraction is a reproducible, externally supplied value in [-1, 1].
    This is an illustration of an observation/classification pipeline, not a
    calibrated confidence interval or a clinical or institutional assessment.
    """
    uncertainty = bound(individual.physiology.observation_uncertainty, 0, 0.25)
    value = bound(observation(individual) + uncertainty * bound(error_fraction, -1, 1))
    lower, upper = bound(value - uncertainty), bound(value + uncertainty)
    if upper < 1/3: category = "laag"
    elif lower >= 2/3: category = "hoog"
    elif lower >= 1/3 and upper < 2/3: category = "midden"
    else: category = "onzeker"
    return SyntheticAssessment(step, value, lower, upper, category)


def group_summary(members, organization):
    if not members:
        return {"mean_opinion": 0.0, "mean_stress": 0.0, "mean_observation": 0.0, "policy": organization.policy}
    n = len(members)
    return {"mean_opinion": sum(i.opinion for i in members) / n,
            "mean_stress": sum(i.stress for i in members) / n,
            "mean_observation": sum(observation(i) for i in members) / n,
            "policy": organization.policy}


def effective_sample_size(n, correlation):
    if n <= 0 or not 0 <= correlation <= 1:
        raise ValueError("n must be positive and correlation between 0 and 1")
    return n / (1 + (n - 1) * correlation)
