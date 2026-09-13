# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tests for the agent loop (no FreeCAD, no model)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import T2GAgent as A    # noqa: E402
import T2GCore as C     # noqa: E402
import T2GProject as P  # noqa: E402

FAILS = []
F = "```"


def check(name, fn):
    try:
        fn()
        print("  ok   %s" % name)
    except Exception as e:  # noqa: BLE001
        FAILS.append((name, e))
        print("  FAIL %s -> %r" % (name, e))


def block(tag, body):
    return F + tag + "\n" + body + "\n" + F


# ---- 1. parsing actions ---------------------------------------------------
def t_parse_actions():
    acts = A.parse_actions(
        "projekt_anlegen: Zylinderkopf V2\n"
        "recherche: Einlasskanal Zylinderkopf; web\n"
        "# ein Kommentar\n"
        "\n"
        "- skill_bedarf: brennraum; Kalotte mit Ventilfenstern\n"
        "2. agent_d:\n")
    assert [a.name for a in acts] == ["projekt_anlegen", "recherche",
                                      "skill_bedarf", "agent_d"], acts
    assert acts[1].args == ["Einlasskanal Zylinderkopf", "web"]
    assert acts[3].args == []


def t_parse_actions_tolerates_case_and_spaces():
    acts = A.parse_actions("  Projekt_Anlegen :  Titel mit Leerzeichen  ")
    assert acts[0].name == "projekt_anlegen"
    assert acts[0].args == ["Titel mit Leerzeichen"], acts[0].args


def t_action_arg_default():
    a = A.Action("x", ["a"])
    assert a.arg(0) == "a" and a.arg(3) == "" and a.arg(3, "fallback") == "fallback"


# ---- 2. reply kinds -------------------------------------------------------
def t_reply_aktion():
    r = A.parse_agent_reply(block("aktion", "projekt_anlegen: X"))
    assert r.kind == "aktion" and r.actions[0].name == "projekt_anlegen"


def t_reply_maske():
    r = A.parse_agent_reply(
        block("maske", "ventil_d;Ventildurchmesser;mm;33;20;50\n"
                       "n_ventile;Ventile je Zylinder;-;4;2;8"),
        C.parse_param_lines)
    assert r.kind == "maske" and len(r.params) == 2
    assert r.params[0][0] == "ventil_d"
    assert isinstance(r.params[1][3], int), "Stückzahl muss ganzzahlig bleiben"


def t_reply_frage_and_fertig():
    assert A.parse_agent_reply(block("frage", "Wie viele Zylinder?")).kind == "frage"
    assert A.parse_agent_reply(block("fertig", "Angelegt.")).kind == "fertig"


def t_reply_python():
    r = A.parse_agent_reply(block("python", "add(Part.makeBox(1,1,1))"))
    assert r.kind == "python" and "makeBox" in r.text


def t_question_beats_action():
    """Hedging must not build anything: the question wins."""
    raw = block("aktion", "projekt_anlegen: X") + "\n" + block("frage", "Sicher?")
    assert A.parse_agent_reply(raw).kind == "frage"


def t_mask_beats_action():
    raw = block("aktion", "projekt_anlegen: X") + "\n" + block("maske", "d;D;mm;10;1;20")
    assert A.parse_agent_reply(raw, C.parse_param_lines).kind == "maske"


def t_bare_question():
    assert A.parse_agent_reply("Wie viele Ventile pro Zylinder?").kind == "frage"


def t_empty_and_garbage():
    for bad in ("", "   "):
        try:
            A.parse_agent_reply(bad)
        except A.AgentError:
            continue
        raise AssertionError("leere Antwort akzeptiert")
    try:
        A.parse_agent_reply("Ich habe hier einen langen Text ohne alles. " * 20)
    except A.AgentError:
        return
    raise AssertionError("Prosa akzeptiert")


def t_empty_block_skipped():
    """An empty ```aktion block must not count as an answer."""
    raw = block("aktion", "") + "\n" + block("fertig", "Nichts zu tun.")
    assert A.parse_agent_reply(raw).kind == "fertig"


# ---- 3. registry ----------------------------------------------------------
def _registry(log):
    reg = A.ActionRegistry()
    reg.register("projekt_anlegen",
                 lambda a: log.append(("neu", a.arg(0))) or "angelegt", "Titel")
    reg.register("explodiert", lambda a: 1 / 0, "Testfehler")
    return reg


def t_registry_runs():
    log = []
    reg = _registry(log)
    obs = reg.run(A.Action("projekt_anlegen", ["Kopf"]))
    assert obs.ok and log == [("neu", "Kopf")], (obs, log)
    assert "OK projekt_anlegen" in obs.render()


def t_registry_catches_errors():
    """A failing action becomes an observation, never an exception."""
    obs = _registry([]).run(A.Action("explodiert"))
    assert not obs.ok and "ZeroDivisionError" in obs.text


def t_registry_unknown_action_lists_options():
    obs = _registry([]).run(A.Action("fliegen"))
    assert not obs.ok and "projekt_anlegen" in obs.text


def t_registry_help_block():
    h = _registry([]).help_block()
    assert "projekt_anlegen: Titel" in h


# ---- 4. run state ---------------------------------------------------------
def t_run_budget():
    run = A.AgentRun(goal="neues Projekt", max_steps=3)
    assert run.should_continue()
    run.step = 3
    assert not run.should_continue() and run.budget_left() == 0


def t_run_stops_on_question():
    run = A.AgentRun(goal="x", max_steps=9)
    run.waiting = "maske"
    assert not run.should_continue()
    run.waiting = ""
    assert run.should_continue()


def t_run_did_work_default():
    """A fresh run has done nothing -- that is what gates a premature 'fertig'."""
    run = A.AgentRun(goal="x")
    assert run.did_work is False
    run.did_work = True
    assert run.did_work is True


def t_run_stop_requested():
    run = A.AgentRun(goal="x")
    run.stop_requested = True
    assert not run.should_continue()


def t_run_observations_windowed():
    run = A.AgentRun(goal="x")
    run.add_observations([A.Observation("a%d" % i, True, "ok") for i in range(30)])
    text = run.recent_observations(5)
    assert text.count("\n") == 4, text
    assert "a29" in text and "a10" not in text


# ---- 5. prompt ------------------------------------------------------------
def t_transcript_in_prompt():
    """What the user already answered must not be asked again."""
    run = A.AgentRun(goal="bitte lege eine baugruppe mit 6 modellen an")
    run.note("agent", "Rückfrage: Welche 6 Modelle?")
    run.note("benutzer", "zylinderkopf, kurbelgehaeuse, oelwanne, "
                         "zylinderkopfhaube, abgaskruemmer, ansaugkruemmer")
    pr = A.build_agent_prompt(run, "", "")
    assert "GESPRÄCHSVERLAUF" in pr, pr
    assert "kurbelgehaeuse" in pr and "abgaskruemmer" in pr, pr
    assert "nicht erneut fragen" in pr


def t_transcript_trimmed_and_clean():
    """Nothing is dropped silently any more -- blanks out, rest condensed."""
    run = A.AgentRun(goal="x")
    for i in range(60):
        run.note("benutzer", "zeile %d" % i)
    run.note("agent", "   ")          # blank lines are dropped
    assert len(run.transcript) == 60, len(run.transcript)
    assert run.needs_compression()
    text = run.recent_transcript(3)
    assert text.count("\n") == 2 and "Benutzer: zeile 59" in text


def t_transcript_empty_prompt():
    pr = A.build_agent_prompt(A.AgentRun(goal="x"), "", "")
    assert "GESPRÄCHSVERLAUF" not in pr


def t_compression_threshold():
    """Only condense when there is a real backlog behind the raw tail."""
    run = A.AgentRun(goal="x", compress_at=6, keep_raw=6, min_to_compress=6)
    for i in range(11):
        run.note("benutzer", "zeile %d" % i)
    assert not run.needs_compression(), "zu frueh: nur 5 alte Zeilen"
    run.note("benutzer", "zeile 11")
    assert run.needs_compression(), "12 Zeilen: 6 alt + 6 roh"
    text, keep = run.split_for_compression()
    assert len(keep) == 6 and text.count("\n") == 5, (len(keep), text)


def t_compression_split_keeps_newest():
    run = A.AgentRun(goal="x", compress_at=3, keep_raw=3, min_to_compress=3)
    for i in range(10):
        run.note("benutzer", "zeile %d" % i)
    text, keep = run.split_for_compression(keep=3)
    assert "zeile 0" in text and "zeile 6" in text, text
    assert [t for _, t in keep] == ["zeile 7", "zeile 8", "zeile 9"], keep
    assert "zeile 9" not in text


def t_compression_applied():
    """After condensing, the facts live in summary and the tail stays raw."""
    run = A.AgentRun(goal="x", compress_at=4, keep_raw=2, min_to_compress=2)
    for i in range(9):
        run.note("benutzer", "zeile %d" % i)
    text, keep = run.split_for_compression(keep=2)
    run.apply_summary("- Baugruppe: 6 Teile\n- Bohrung 86 mm", keep)
    assert len(run.transcript) == 2
    assert not run.needs_compression()
    pr = A.build_agent_prompt(run, "", "")
    assert "BISHER GEKLÄRT" in pr and "Bohrung 86 mm" in pr, pr
    assert "zeile 8" in pr          # the raw tail is still there
    assert "zeile 0" not in pr      # the old raw lines are gone


def t_compression_summary_kept_on_next_round():
    run = A.AgentRun(goal="x")
    run.apply_summary("- erste Fassung", [])
    run.apply_summary("", [("benutzer", "neu")])   # empty must not wipe it
    assert run.summary == "- erste Fassung"


def t_prompt_contains_state():
    run = A.AgentRun(goal="neues Zylinderkopfprojekt", max_steps=8)
    run.add_observations([A.Observation("projekt_anlegen", True, "angelegt")])
    run.step = 1
    pr = A.build_agent_prompt(run, "PROJEKT: Kopf\nAuftrag: x",
                              "Objekte im Dokument (0)",
                              skills=["bruecke", "einlasskanal"])
    assert "neues Zylinderkopfprojekt" in pr
    assert "PROJEKT: Kopf" in pr
    assert "OK projekt_anlegen" in pr
    assert "bruecke, einlasskanal" in pr
    assert "Schritt 2 von höchstens 8" in pr


def t_prompt_lists_tools():
    """The agent must know what the installation already offers."""
    pr = A.build_agent_prompt(A.AgentRun(goal="zahnrad"), "", "",
                              tools="- [Befehl] FCGear_InvoluteGear: Zahnrad\n"
                                    "- [Makro] Bohrbild: Lochbild setzen")
    assert "WERKZEUGE" in pr and "FCGear_InvoluteGear" in pr, pr
    assert "statt selbst nachbauen" in pr


def t_prompt_without_tools():
    pr = A.build_agent_prompt(A.AgentRun(goal="x"), "", "", tools="   ")
    assert "WERKZEUGE" not in pr


def t_prompt_without_project():
    pr = A.build_agent_prompt(A.AgentRun(goal="x"), "", "", skills=[])
    assert "Kein Projekt geöffnet." in pr


def t_prompt_carries_answer():
    run = A.AgentRun(goal="x")
    pr = A.build_agent_prompt(run, "", "", answered="ventil_d = 33 mm")
    assert "ventil_d = 33 mm" in pr and "ANTWORT DES BENUTZERS" in pr


# ---- 6. mask round trip ---------------------------------------------------
def t_mask_to_project_and_back():
    """A form the model asked for must land in the project as parameters."""
    import tempfile
    proj = P.Project.create(tempfile.mkdtemp(prefix="t2g_agent_"), "Maskentest")
    reply = A.parse_agent_reply(
        block("maske", "ventil_d_ein;Einlassventil;mm;33;20;50\n"
                       "n_ventile;Ventile je Zylinder;-;4;2;8"),
        C.parse_param_lines)
    proj.set_params([P.param_from_row(r) for r in reply.params])
    assert [p.name for p in proj.params] == ["ventil_d_ein", "n_ventile"]
    problems = proj.answer_mask({"ventil_d_ein": 35.5, "n_ventile": 4})
    assert problems == [], problems
    assert proj.param("ventil_d_ein").value == 35.5
    assert proj.param("n_ventile").value == 4
    # and the values reach the next prompt
    assert "35.5 mm" in proj.as_prompt_block()


# ---- 7. loop breakers -----------------------------------------------------
def _same_question(a, b):
    """Mirror of T2GPanel._same_question (that module needs FreeCAD)."""
    import difflib
    import re

    def norm(t):
        return " ".join(re.findall(r"[a-zäöüß0-9]+", (t or "").lower()))
    x, y = norm(a), norm(b)
    if not x or not y:
        return False
    return difflib.SequenceMatcher(None, x, y).ratio() >= 0.75


def t_same_question_detected():
    a = ("Die Brücke im Dokument ist 2000 mm lang, der Parameter sagt 3006 mm. "
         "Soll ich die bestehende Brücke verlängern oder eine neue bauen?")
    b = ("Die aktuelle Brücke im Dokument ist 2000 mm lang, der Parameter steht "
         "auf 3006 mm. Soll ich die bestehende Brücke verlängern oder eine "
         "komplett neue bauen?")
    assert _same_question(a, b), "Wiederholung nicht erkannt"


def t_different_questions_not_merged():
    a = "Welche 6 Modelle sollen in die Baugruppe?"
    b = "Welchen Durchmesser soll die Bohrung haben?"
    assert not _same_question(a, b)
    assert not _same_question("", "irgendwas")


PROMISE_WORDS = ("ich lerne", "ich baue", "ich erzeuge", "ich erstelle",
                 "ich lege", "ich setze", "ich starte", "werde ich",
                 "als nächstes", "als naechstes", "im nächsten schritt",
                 "im naechsten schritt", "danach baue", "danach lerne")


def t_promise_detected():
    """An announcement must not pass as a finished job."""
    echt = ('Der Skill "lavalduese" existiert noch nicht – ich lerne ihn jetzt. '
            'Danach baue ich ihn mit deinen Parametern ins Dokument.')
    assert any(w in echt.lower() for w in PROMISE_WORDS), echt


def t_finished_text_not_flagged():
    fertig = ("Baugruppe „Motorenbau“ mit 6 Platzhaltern angelegt, "
              "Parameter gesetzt, agent.d geschrieben.")
    assert not any(w in fertig.lower() for w in PROMISE_WORDS), fertig


def t_promise_counter():
    run = A.AgentRun(goal="x")
    assert run.promises == 0
    run.promises += 1
    assert run.promises == 1


def t_rejection_counter():
    run = A.AgentRun(goal="x")
    assert run.rejections == 0 and run.last_question == ""
    run.rejections += 1
    run.last_question = "Welche Teile?"
    assert run.rejections == 1


print("Running T2G agent tests\n")
check("Aktionen parsen", t_parse_actions)
check("Aktionen: Gross/Klein, Leerzeichen", t_parse_actions_tolerates_case_and_spaces)
check("Action.arg mit Standardwert", t_action_arg_default)
check("Antwort: aktion", t_reply_aktion)
check("Antwort: maske", t_reply_maske)
check("Antwort: frage/fertig", t_reply_frage_and_fertig)
check("Antwort: python", t_reply_python)
check("Frage schlaegt Aktion", t_question_beats_action)
check("Maske schlaegt Aktion", t_mask_beats_action)
check("Frage ohne Fence", t_bare_question)
check("leer und Muell abgelehnt", t_empty_and_garbage)
check("leerer Block wird uebersprungen", t_empty_block_skipped)
check("Registry fuehrt aus", t_registry_runs)
check("Registry faengt Fehler", t_registry_catches_errors)
check("Registry nennt Alternativen", t_registry_unknown_action_lists_options)
check("Registry-Hilfe", t_registry_help_block)
check("Schrittbudget", t_run_budget)
check("haelt bei Rueckfrage", t_run_stops_on_question)
check("Wiederholte Frage erkannt", t_same_question_detected)
check("Verschiedene Fragen bleiben getrennt", t_different_questions_not_merged)
check("Ankuendigung erkannt", t_promise_detected)
check("Fertigmeldung nicht faelschlich markiert", t_finished_text_not_flagged)
check("Ankuendigungszaehler", t_promise_counter)
check("Zurueckweisungszaehler", t_rejection_counter)
check("did_work anfangs falsch", t_run_did_work_default)
check("Stop-Wunsch", t_run_stop_requested)
check("Beobachtungsfenster", t_run_observations_windowed)
check("Verdichtung: Schwelle", t_compression_threshold)
check("Verdichtung: Neuestes bleibt roh", t_compression_split_keeps_newest)
check("Verdichtung: angewandt", t_compression_applied)
check("Verdichtung: leere Antwort loescht nichts", t_compression_summary_kept_on_next_round)
check("Verlauf steht im Prompt", t_transcript_in_prompt)
check("Verlauf gekuerzt und sauber", t_transcript_trimmed_and_clean)
check("ohne Verlauf kein Abschnitt", t_transcript_empty_prompt)
check("Prompt enthaelt Zustand", t_prompt_contains_state)
check("Prompt nennt Werkzeuge", t_prompt_lists_tools)
check("Prompt ohne Werkzeuge", t_prompt_without_tools)
check("Prompt ohne Projekt", t_prompt_without_project)
check("Prompt traegt Antwort", t_prompt_carries_answer)
check("Maske -> Projekt -> Prompt", t_mask_to_project_and_back)

print("\nFAILS:", len(FAILS))
for name, e in FAILS:
    print("  -", name, "->", repr(e))
if FAILS:
    sys.exit(1)
print("ALL AGENT TESTS PASSED")
