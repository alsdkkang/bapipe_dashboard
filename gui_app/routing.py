"""Pure phase-resolution for the dashboard's top-level state machine."""

PHASES = ("welcome", "records", "wizard", "loading", "app", "guide")


def resolve_phase(onboarded, session_phase):
    """Which screen to show this run.

    An explicit, valid `session_phase` always wins. Otherwise a first-time user
    (not onboarded) sees "welcome"; a returning user sees "records".
    """
    if session_phase in PHASES:
        return session_phase
    return "records" if onboarded else "welcome"
