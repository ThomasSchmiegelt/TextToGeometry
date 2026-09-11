#!/usr/bin/env bash
# start.sh — startet FreeCAD mit dem TextToGeometry-Workbench
#
# Aufruf:
#   ./start.sh            # GUI starten
#   ./start.sh test       # alle Testsuiten mit FreeCADCmd ausführen
#   ./start.sh sync       # Development-Ordner nach FreeCAD-Mod-Pfad kopieren

set -euo pipefail
MODE="${1:-gui}"

DEV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Pfade ----------------------------------------------------------------
FREECAD="${FREECAD:-$HOME/freecad_1.1_quellcode/build/release/bin/FreeCAD}"
FREECAD_CMD="${FREECAD_CMD:-$HOME/freecad_1.1_quellcode/build/release/bin/FreeCADCmd}"
PI_BIN="${T2G_PI_BIN:-$HOME/.npm-global/bin/pi}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen-gross:latest}"

freecad_root="${HOME}/.local/share/FreeCAD"
# Versionierter Mod-Pfad (1.1-Standard, via T2G_FREECAD_VER überschreibbar)
fc_ver="${T2G_FREECAD_VER:-1-1}"
if [ -d "${freecad_root}/v${fc_ver}/Mod" ]; then
    MOD_DIR="${freecad_root}/v${fc_ver}/Mod/TextToGeometry"
else
    MOD_DIR="${freecad_root}/Mod/TextToGeometry"
    say "Achtung: v${fc_ver}-Mod-Verzeichnis fehlt, nutze $MOD_DIR"
fi

# --- Helfer ---------------------------------------------------------------
say() { printf '\033[1;36m[TextToGeometry]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[TextToGeometry] FEHLER:\033[0m %s\n' "$*" >&2; exit 1; }

check_prereqs() {
    local missing=0
    [ -x "$FREECAD" ]     || { say "FreeCAD fehlt: $FREECAD"; missing=1; }
    [ -x "$FREECAD_CMD" ] || { say "FreeCADCmd fehlt: $FREECAD_CMD"; missing=1; }
    [ -x "$PI_BIN" ]      || { say "pi-CLI fehlt: $PI_BIN (optional, T2G_PI_BIN setzen)"; missing=1; }
    if command -v curl >/dev/null 2>&1; then
        if ! curl -fsS -o /dev/null --max-time 2 "http://localhost:11434/api/tags"; then
            say "Ollama läuft nicht auf localhost:11434 (optional, für HTTP-Backend)"
            missing=1
        fi
    fi
    [ "$missing" = 0 ] || say "Einige optionale Abhängigkeiten fehlen — GUI startet trotzdem, falls FreeCAD da ist."
    [ -x "$FREECAD" ] || fail "FreeCAD-Binary nicht gefunden: $FREECAD"
}

sync_src() {
    say "Synchronisiere $DEV_DIR -> $MOD_DIR"
    mkdir -p "$MOD_DIR"
    cp -v \
        "$DEV_DIR"/__init__.py \
        "$DEV_DIR"/Init.py \
        "$DEV_DIR"/InitGui.py \
        "$DEV_DIR"/T2GCore.py \
        "$DEV_DIR"/T2GCommand.py \
        "$DEV_DIR"/T2GSkills.py \
        "$DEV_DIR"/package.xml \
        "$DEV_DIR"/CMakeLists.txt \
        "$DEV_DIR"/README.md \
        "$DEV_DIR"/DOKUMENTATION.md \
        "$DEV_DIR"/test_core.py \
        "$DEV_DIR"/test_ext.py \
        "$DEV_DIR"/test_skills.py \
        "$MOD_DIR"/
    cp -rv "$DEV_DIR"/Resources "$MOD_DIR"/ >/dev/null
    cp -rv "$DEV_DIR"/Skills    "$MOD_DIR"/ >/dev/null
    find "$MOD_DIR" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
    say "Sync fertig."
}

run_tests() {
    [ -x "$FREECAD_CMD" ] || fail "FreeCADCmd nicht gefunden: $FREECAD_CMD"
    local rc_all=0
    for t in test_core.py test_ext.py test_skills.py; do
        say "Starte $t …"
        if ( cd "$DEV_DIR" && "$FREECAD_CMD" "$t"; ); then
            say "  ✔ $t PASS"
        else
            say "  ✘ $t FAIL"
            rc_all=1
        fi
    done
    return $rc_all
}

run_gui() {
    export T2G_PI_BIN="$PI_BIN"
    export T2G_OLLAMA_MODEL="$OLLAMA_MODEL"
    say "Starte FreeCAD-GUI (Workbench: TextToGeometry) …"
    exec env DISPLAY="${DISPLAY:-:0}" "$FREECAD"
}

case "$MODE" in
    sync)  sync_src ;;
    test)  run_tests ;;
    gui)   check_prereqs; run_gui ;;
    help|--help|-h)
        cat <<EOF
start.sh [gui|sync|test]
  gui   (Standard)  startet die FreeCAD-GUI mit der Workbench
  sync          Development-Dateien in den FreeCAD-Mod-Pfad kopieren
  test          alle Tests unter FreeCADCmd ausführen
EOF
        ;;
    *) fail "Unbekannter Modus: $MODE  (gui|sync|test|help)" ;;
esac
