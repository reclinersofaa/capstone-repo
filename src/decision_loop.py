import random
from .agent import Agent


def simulate_email(agent: Agent, cues: list[str], rng: random.Random = None) -> dict:
    """
    Run the decision loop for one agent reading one email.

    The agent iterates through the cue list (shuffled) and tries to perceive
    each cue. Whether a cue is perceived depends on the agent's trait-differentiated
    Flawed Perception Level (FPL): if random draw > FPL, the cue registers.

    The loop stops early when:
      - suspicion_counter reaches suspicion_threshold → "reported"
      - cues scanned reaches max_cues_processed     → "clicked"

    Returns
    -------
    dict with keys:
        decision          : "clicked" | "reported"
        suspicion_counter : int  (how high the counter got)
        cues_scanned      : int  (how many cues the agent looked at)
        cues_perceived    : list (which cues actually registered)
        total_fatigue     : float
        final_jp          : float
        fpl               : float (base flawed perception level)
    """
    if rng is None:
        rng = random.Random()

    total_fatigue = agent.compute_total_fatigue()
    final_jp = agent.compute_job_performance()
    base_fpl = agent.compute_flawed_perception_level()

    suspicion_counter = 0
    cues_perceived: list[str] = []

    shuffled = cues.copy()
    rng.shuffle(shuffled)

    i = -1  # guard: keeps cues_scanned=0 when email has no cues
    for i, cue in enumerate(shuffled):
        if i >= agent.max_cues_processed:
            break

        cue_fpl = agent.get_cue_fpl(cue)

        # Agent perceives the cue if random draw beats their flawed perception
        if rng.random() > cue_fpl:
            cues_perceived.append(cue)
            suspicion_counter += 1

        if suspicion_counter >= agent.suspicion_threshold:
            break

    decision = "reported" if suspicion_counter >= agent.suspicion_threshold else "clicked"

    return {
        "decision": decision,
        "suspicion_counter": suspicion_counter,
        "cues_scanned": min(len(shuffled), agent.max_cues_processed, i + 1),
        "cues_perceived": cues_perceived,
        "total_fatigue": round(total_fatigue, 3),
        "final_jp": round(final_jp, 3),
        "fpl": round(base_fpl, 3),
    }


def simulate_email_across_day(
    agent: Agent,
    cues: list[str],
    hours: list[float] = None,
    rng: random.Random = None,
) -> list[dict]:
    """
    Run the same email through one agent at multiple points during the workday.
    Returns a list of result dicts, one per hour.
    """
    if hours is None:
        hours = [8.0, 10.0, 12.0, 14.0, 16.0]
    if rng is None:
        rng = random.Random()

    results = []
    for hour in hours:
        agent.advance_workday(hour)
        result = simulate_email(agent, cues, rng=rng)
        result["workday_hour"] = hour
        results.append(result)
    return results
