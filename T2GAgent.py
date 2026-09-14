# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""The agent loop behind the chat window.

The chat is the main way in: the user says "neues Zylinderkopfprojekt" and the
model works through it in steps -- research, create the project, agree the
parameters, note which part depends on which, propose skills and tools -- and
comes back with a question, a form to fill in, or a summary.

One turn of the loop:

    prompt (project state + document + observations)
        -> model answers with exactly one block
        -> ```aktion   run the actions, feed the results back, keep going
           ```maske    ask the user to fill in a parameter form, stop
           ```frage    ask a free-text question, stop
           ```python   change the open document (T2GCore.OpRecorder), keep going
           ```fertig   summary, stop

Actions are supplied by the caller (the GUI owns FreeCAD, the project and the
skill engine), so this module stays importable and testable on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_STEPS_DEFAULT = 12


class AgentError(Exception):
    pass


@dataclass
class Action:
    name: str
    args: list = field(default_factory=list)
    raw: str = ""

    def arg(self, i: int, default: str = "") -> str:
        return self.args[i] if i < len(self.args) else default


@dataclass
class AgentReply:
    kind: str                       # aktion | frage | maske | python | fertig
    text: str = ""
    actions: list = field(default_factory=list)
    params: list = field(default_factory=list)      # for kind == "maske"


@dataclass
class Observation:
    action: str
    ok: bool
    text: str

    def render(self) -> str:
        return f"{'OK' if self.ok else 'FEHLER'} {self.action}: {self.text}"


#: Block tag -> reply kind. Order matters: a question or a form wins over
#: actions, so a model that hedges never builds something half-specified.
_BLOCK_ORDER = ("frage", "maske", "fertig", "aktion", "python")

_BLOCK_ALIASES = {
    "frage": ("frage", "question"),
    "maske": ("maske", "formular", "parameter"),
    "fertig": ("fertig", "zusammenfassung", "done"),
    "aktion": ("aktion", "aktionen", "action"),
    "python": ("python", "py"),
}


def _find_block(text: str, tags) -> "str | None":
    for tag in tags:
        m = re.search(r"```" + tag + r"[ \t]*\n(.*?)\n?[ \t]*```",
                      text or "", re.DOTALL | re.I)
        if m:
            return m.group(1)
    return None


def parse_actions(block: str) -> list:
    """``name: arg; arg`` per line -> [Action]. Empty lines and #-comments out."""
    out = []
    for line in (block or "").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        raw = re.sub(r"^[-*\d.]+\s+", "", raw)
        if ":" not in raw:
            name, rest = raw.strip(), ""
        else:
            name, rest = raw.split(":", 1)
        name = re.sub(r"[^a-z0-9_]", "_", name.strip().lower()).strip("_")
        if not name:
            continue
        args = [a.strip() for a in rest.split(";")] if rest.strip() else []
        out.append(Action(name=name, args=[a for a in args if a != ""], raw=raw))
    return out


def parse_agent_reply(raw: str, param_parser=None) -> AgentReply:
    """Turn one model answer into exactly one reply kind."""
    text = raw or ""
    if not text.strip():
        raise AgentError("Leere Antwort vom Modell.")
    for kind in _BLOCK_ORDER:
        block = _find_block(text, _BLOCK_ALIASES[kind])
        if block is None:
            continue
        block = block.strip()
        if not block:
            continue
        if kind == "aktion":
            actions = parse_actions(block)
            if not actions:
                continue
            return AgentReply(kind="aktion", text=block, actions=actions)
        if kind == "maske":
            params = param_parser(block) if param_parser else []
            if not params:
                continue
            return AgentReply(kind="maske", text=block, params=params)
        return AgentReply(kind=kind, text=block)
    # No fence at all: a short question is still a question.
    stripped = text.strip()
    if "?" in stripped and len(stripped) < 400:
        return AgentReply(kind="frage", text=stripped)
    raise AgentError("Antwort ohne verwertbaren Block:\n" + stripped[:300])


class ActionRegistry:
    """The verbs the agent may use; the caller supplies what they do."""

    def __init__(self) -> None:
        self._fns: dict = {}
        self._help: dict = {}

    def register(self, name: str, fn, help_text: str = "") -> None:
        self._fns[name] = fn
        self._help[name] = help_text

    def __contains__(self, name) -> bool:
        return name in self._fns

    def names(self) -> list:
        return sorted(self._fns)

    def help_block(self) -> str:
        return "\n".join(f"  {n}: {self._help.get(n, '')}"
                         for n in self.names())

    def run(self, action: "Action") -> Observation:
        fn = self._fns.get(action.name)
        if fn is None:
            return Observation(action.name, False,
                               "unbekannte Aktion; erlaubt sind: "
                               + ", ".join(self.names()))
        try:
            result = fn(action)
        except Exception as e:  # noqa: BLE001  -- surfaced to the model
            return Observation(action.name, False, f"{type(e).__name__}: {e}")
        return Observation(action.name, True, str(result or "erledigt"))


@dataclass
class AgentRun:
    """State of one chat request being worked on."""

    goal: str = ""
    step: int = 0
    max_steps: int = MAX_STEPS_DEFAULT
    observations: list = field(default_factory=list)   # [Observation]
    transcript: list = field(default_factory=list)     # [(kind, text)]
    finished: bool = False
    waiting: str = ""            # "frage" | "maske" while the user is asked
    stop_requested: bool = False
    #: True as soon as an action or a document change actually ran. A model
    #: that only *claims* to have done something must not end the run.
    did_work: bool = False
    #: How often a claimed-but-empty "fertig" was sent back.
    rejections: int = 0
    #: The question asked last, to notice it being asked again.
    last_question: str = ""
    #: How often the model announced a step instead of taking it.
    promises: int = 0
    #: Condensed older history. Plain truncation would drop exactly the things
    #: that matter (a list of parts named ten turns ago), so the old entries
    #: are summarised into this and then removed.
    summary: str = ""
    #: Transcript length from which condensing is considered.
    compress_at: int = 16
    #: How many newest entries always stay verbatim. Condensing only starts
    #: when there is a real backlog behind them -- summarising one stray line
    #: produces "Zahlen: keine" noise and costs a round trip for nothing.
    keep_raw: int = 6
    #: Fewest entries worth condensing at once.
    min_to_compress: int = 6

    def note(self, kind: str, text: str) -> None:
        """Record one line of the conversation.

        Without this the model re-asks what it was already told: the prompt
        carries only the goal, the last answer and the observations, so a list
        the user typed three steps ago would otherwise be gone.
        """
        text = (text or "").strip()
        if not text:
            return
        self.transcript.append((kind, text))

    def needs_compression(self) -> bool:
        backlog = len(self.transcript) - self.keep_raw
        return (len(self.transcript) > max(4, self.compress_at)
                and backlog >= self.min_to_compress)

    def split_for_compression(self, keep: "int | None" = None) -> "tuple[str, list]":
        """(text to condense, entries to keep) -- oldest go, newest stay."""
        keep = self.keep_raw if keep is None else keep
        if not self.needs_compression():
            return "", list(self.transcript)
        old = self.transcript[:-keep] if keep else list(self.transcript)
        names = {"benutzer": "Benutzer", "agent": "Agent", "system": "System"}
        text = "\n".join("%s: %s" % (names.get(k, k), t) for k, t in old)
        return text, self.transcript[-keep:] if keep else []

    def apply_summary(self, summary: str, keep: list) -> None:
        self.summary = (summary or "").strip() or self.summary
        self.transcript = list(keep)

    def recent_transcript(self, count: int = 14) -> str:
        if not self.transcript:
            return ""
        names = {"benutzer": "Benutzer", "agent": "Du", "system": "System"}
        return "\n".join("%s: %s" % (names.get(k, k), t)
                          for k, t in self.transcript[-count:])

    def add_observations(self, obs: list) -> None:
        self.observations.extend(obs)

    def recent_observations(self, count: int = 12) -> str:
        if not self.observations:
            return ""
        return "\n".join(o.render() for o in self.observations[-count:])

    def budget_left(self) -> int:
        return max(0, self.max_steps - self.step)

    def should_continue(self) -> bool:
        return (not self.finished and not self.stop_requested
                and not self.waiting and self.budget_left() > 0)


def build_agent_prompt(run: "AgentRun", project_block: str, doc_context: str,
                       user_msg: str = "", skills: list | None = None,
                       answered: str = "", tools: str = "") -> str:
    """Everything the model needs for the next step, and nothing else."""
    parts = []
    if project_block.strip():
        parts += ["PROJEKTZUSTAND", project_block.strip(), ""]
    else:
        parts += ["PROJEKTZUSTAND", "Kein Projekt geöffnet.", ""]
    if doc_context.strip():
        parts += ["FREECAD-DOKUMENT", doc_context.strip(), ""]
    if skills:
        # A list of names is not enough: the agent needs the parameters and
        # above all the axis a skill builds along, or it cannot place the part.
        block = skills if isinstance(skills, str) else ", ".join(skills)
        parts += ["VERFÜGBARE SKILLS (Achse = Richtung, in der der Skill baut; "
                  "passt sie nicht zur Lage im Dokument, mit dreh_x/y/z beim "
                  "skill_bauen drehen)", block, ""]
    if tools.strip():
        parts += ["WERKZEUGE DIESER INSTALLATION (statt selbst nachbauen). "
                  "Liefert eine Funktion die ganze Baugruppe, dann rufe SIE "
                  "auf, statt die Teile einzeln zu setzen - sie rechnet die "
                  "Masse und Lagen selbst:\n"
                  "  werkzeug_aufrufen: modul.funktion;arg=wert;arg=wert",
                  tools.strip(), ""]
    if run.goal:
        parts += ["AUFTRAG DES BENUTZERS", run.goal.strip(), ""]
    if run.summary.strip():
        parts += ["BISHER GEKLÄRT (verdichtet – gilt weiterhin)",
                  run.summary.strip(), ""]
    talk = run.recent_transcript()
    if talk:
        parts += ["GESPRÄCHSVERLAUF (schon geklärt – nicht erneut fragen)",
                  talk, ""]
    if answered.strip():
        parts += ["ANTWORT DES BENUTZERS", answered.strip(), ""]
    obs = run.recent_observations()
    if obs:
        parts += ["ERGEBNISSE DEINER LETZTEN SCHRITTE", obs, ""]
    if user_msg.strip() and user_msg.strip() != run.goal.strip():
        parts += ["NEUE ANWEISUNG", user_msg.strip(), ""]
    parts += [f"Schritt {run.step + 1} von höchstens {run.max_steps}. "
              "Führe den nächsten sinnvollen Schritt aus oder schließe ab."]
    return "\n".join(parts)


__all__ = [
    "Action", "AgentReply", "AgentRun", "AgentError", "ActionRegistry",
    "Observation", "parse_actions", "parse_agent_reply", "build_agent_prompt",
    "MAX_STEPS_DEFAULT",
]
