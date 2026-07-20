"""Parser fuer die Command-Line.

Wandelt Tokens (siehe lexer.py) in eine Command-Instanz um.
Jede Command-Instanz besitzt eine execute(state)-Methode und
liefert ein CommandResult zurueck.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from .lexer import Token, TokenType, tokenize


# ── AST / Selektion ──────────────────────────────────────────────────────────

@dataclass
class SelectionExpr:
    """Beschreibt eine Fixture-Selektion."""
    add: list[int] = field(default_factory=list)
    ranges: list[tuple[int, int]] = field(default_factory=list)
    excludes: list[int] = field(default_factory=list)
    all_fixtures: bool = False

    def is_empty(self) -> bool:
        return (not self.add and not self.ranges and not self.all_fixtures)

    def resolve(self, all_fids: list[int]) -> list[int]:
        try:
            if self.all_fixtures:
                sel = set(all_fids)
            else:
                sel = set()
                for f in self.add:
                    if f in all_fids:
                        sel.add(f)
                for s, e in self.ranges:
                    lo, hi = (s, e) if s <= e else (e, s)
                    # Ueber die GEPATCHTEN fids iterieren, nicht ueber range(lo,hi+1):
                    # ein Tippfehler wie `1 thru 999999999` iterierte sonst
                    # milliardenfach und fror die GUI ein (DoS per Command-Line).
                    for f in all_fids:
                        if lo <= f <= hi:
                            sel.add(f)
            for ex in self.excludes:
                sel.discard(ex)
            return sorted(sel)
        except Exception as e:
            print(f"[cmdline.parser] SelectionExpr.resolve error: {e}")
            return []


# ── CommandResult ────────────────────────────────────────────────────────────

@dataclass
class CommandResult:
    ok: bool
    message: str


class Command:
    def execute(self, state) -> CommandResult:
        raise NotImplementedError


# ── Konkrete Commands ────────────────────────────────────────────────────────

@dataclass
class SetValueCommand(Command):
    selection: SelectionExpr
    attribute: str
    value_pct: int | None = None
    value_raw: int | None = None

    def execute(self, state) -> CommandResult:
        try:
            all_fids = [f.fid for f in state.get_patched_fixtures()]
            if self.selection.is_empty():
                # Fallback: aktuell gespeicherte Selektion verwenden
                fids = list(getattr(state, "selected_fids", []) or [])
            else:
                fids = self.selection.resolve(all_fids)
            if not fids:
                return CommandResult(False, "Keine Fixtures selektiert")
            if self.value_pct is not None:
                pct = max(0, min(100, int(self.value_pct)))
                val = int(round(pct * 255 / 100))
            else:
                val = max(0, min(255, int(self.value_raw or 0)))
            for fid in fids:
                state.set_programmer_value(fid, self.attribute, val)
            return CommandResult(True, f"{len(fids)}x {self.attribute}={val}")
        except Exception as e:
            return CommandResult(False, f"SetValue Fehler: {e}")


@dataclass
class SelectionCommand(Command):
    """Nur Selektion ohne Wert (z.B. '1 thru 5')."""
    selection: SelectionExpr

    def execute(self, state) -> CommandResult:
        try:
            all_fids = [f.fid for f in state.get_patched_fixtures()]
            fids = self.selection.resolve(all_fids)
            if not hasattr(state, "selected_fids"):
                state.selected_fids = []
            state.selected_fids = fids
            if not fids:
                return CommandResult(True, "Selektion leer")
            return CommandResult(True, f"Selektiert: {len(fids)} ({_short_list(fids)})")
        except Exception as e:
            return CommandResult(False, f"Selektion Fehler: {e}")


@dataclass
class ClearCommand(Command):
    def execute(self, state) -> CommandResult:
        try:
            state.clear_programmer()
            if hasattr(state, "selected_fids"):
                state.selected_fids = []
            return CommandResult(True, "Programmer geleert")
        except Exception as e:
            return CommandResult(False, f"Clear Fehler: {e}")


@dataclass
class GoCommand(Command):
    slot: int = 1

    def execute(self, state) -> CommandResult:
        try:
            # Executor-Slots sind 1-basiert; get_executor(0) wuerde per
            # Python-Negativindex den LETZTEN Executor treffen.
            if self.slot < 1:
                return CommandResult(False, f"Ungültiger Executor {self.slot} (1-basiert)")
            pe = state.playback_engine
            if pe is None:
                # Fallback: Cue-Stack direkt
                stacks = getattr(state, "cue_stacks", [])
                if stacks:
                    stacks[0].go()
                    return CommandResult(True, "GO (Stack 1)")
                return CommandResult(False, "Kein Playback-Engine")
            ex = pe.get_executor(self.slot)
            ex.press_btn("go")
            return CommandResult(True, f"GO Exec {self.slot}")
        except Exception as e:
            return CommandResult(False, f"GO Fehler: {e}")


@dataclass
class BackCommand(Command):
    slot: int = 1

    def execute(self, state) -> CommandResult:
        try:
            if self.slot < 1:   # 1-basiert; 0 waere Negativindex (letzter Executor)
                return CommandResult(False, f"Ungültiger Executor {self.slot} (1-basiert)")
            pe = state.playback_engine
            if pe is None:
                stacks = getattr(state, "cue_stacks", [])
                if stacks:
                    stacks[0].back()
                    return CommandResult(True, "BACK (Stack 1)")
                return CommandResult(False, "Kein Playback")
            ex = pe.get_executor(self.slot)
            ex.press_btn("back")
            return CommandResult(True, f"BACK Exec {self.slot}")
        except Exception as e:
            return CommandResult(False, f"BACK Fehler: {e}")


@dataclass
class StopCommand(Command):
    slot: int | None = None

    def execute(self, state) -> CommandResult:
        try:
            pe = state.playback_engine
            if pe is None:
                return CommandResult(False, "Kein Playback")
            if self.slot is None:
                # „Stop All" = Panik-Superset (wie der STOP_ALL-Button): Cuestacks UND
                # FunctionManager-Funktionen (getoggelte Szenen/EFX/Programmer-Matrizen).
                pe.stop_all()
                try:
                    state.function_manager.stop_all()
                except Exception:
                    pass
                return CommandResult(True, "Stop All")
            if self.slot < 1:   # 1-basiert; 0 waere Negativindex (letzter Executor)
                return CommandResult(False, f"Ungültiger Executor {self.slot} (1-basiert)")
            ex = pe.get_executor(self.slot)
            ex.press_btn("stop")
            return CommandResult(True, f"Stop Exec {self.slot}")
        except Exception as e:
            return CommandResult(False, f"Stop Fehler: {e}")


@dataclass
class BlackoutCommand(Command):
    def execute(self, state) -> CommandResult:
        try:
            om = state.output_manager
            new_val = not bool(getattr(om, "_blackout", False))
            om.set_blackout(new_val)
            return CommandResult(True, "Blackout " + ("AN" if new_val else "AUS"))
        except Exception as e:
            return CommandResult(False, f"Blackout Fehler: {e}")


@dataclass
class RecordCueCommand(Command):
    number: float = 1.0

    def execute(self, state) -> CommandResult:
        try:
            stacks = getattr(state, "cue_stacks", [])
            if not stacks:
                return CommandResult(False, "Keine Cueliste vorhanden")
            cue = state.record_cue(stacks[0], float(self.number),
                                   f"Cue {self.number}")
            return CommandResult(True, f"Cue {self.number} aufgenommen")
        except Exception as e:
            return CommandResult(False, f"Record Fehler: {e}")


@dataclass
class RecordSceneCommand(Command):
    name: str = ""

    def execute(self, state) -> CommandResult:
        try:
            from src.core.engine.scene import Scene
            from src.core.app_state import get_channels_for_patched
            prog = getattr(state, "programmer", {})
            if not prog:
                return CommandResult(False, "Programmer leer — nichts zu speichern")
            scene = Scene(name=self.name or "Neue Szene")
            # Map (fid, attribute) -> (fid, 1-basierte Kanal-Nr.) -> value
            patched_by_fid = {f.fid: f for f in state.get_patched_fixtures()}
            count = 0
            for fid, attrs in prog.items():
                fixture = patched_by_fid.get(fid)
                if not fixture:
                    continue
                try:
                    chans = get_channels_for_patched(fixture)
                except Exception:
                    chans = []
                attr_to_ch = {ch.attribute: ch.channel_number for ch in chans}
                for attr, val in attrs.items():
                    ch_no = attr_to_ch.get(attr)
                    if ch_no is None:
                        continue
                    scene.set_value(fid, int(ch_no), int(val))
                    count += 1
            fm = getattr(state, "function_manager", None)
            if fm is not None:
                try:
                    if hasattr(fm, "add"):
                        fm.add(scene)
                    elif hasattr(fm, "add_function"):
                        fm.add_function(scene)
                except Exception as e:
                    print(f"[cmdline] scene add error: {e}")
            return CommandResult(True, f"Scene '{scene.name}' gespeichert ({count} Werte)")
        except Exception as e:
            return CommandResult(False, f"Scene-Record Fehler: {e}")


@dataclass
class PageCommand(Command):
    page: int | None = None    # 1-basiert (Anzeige)
    delta: int = 0             # +1 / -1

    def execute(self, state) -> CommandResult:
        try:
            pe = state.playback_engine
            if pe is None:
                return CommandResult(False, "Kein Playback")
            if self.page is not None:
                pe.set_page(max(0, self.page - 1))
            else:
                pe.set_page(pe.current_page + self.delta)
            return CommandResult(True, f"Page {pe.current_page + 1}")
        except Exception as e:
            return CommandResult(False, f"Page Fehler: {e}")


@dataclass
class HighlightCommand(Command):
    def execute(self, state) -> CommandResult:
        try:
            sel = list(getattr(state, "selected_fids", []) or [])
            if not sel:
                sel = [f.fid for f in state.get_patched_fixtures()]
            for fid in sel:
                state.set_programmer_value(fid, "intensity", 255)
                state.set_programmer_value(fid, "color_r", 255)
                state.set_programmer_value(fid, "color_g", 255)
                state.set_programmer_value(fid, "color_b", 255)
            return CommandResult(True, f"Highlight {len(sel)} Fixtures")
        except Exception as e:
            return CommandResult(False, f"Highlight Fehler: {e}")


@dataclass
class LowlightCommand(Command):
    def execute(self, state) -> CommandResult:
        try:
            sel = set(getattr(state, "selected_fids", []) or [])
            count = 0
            for f in state.get_patched_fixtures():
                if f.fid not in sel:
                    state.set_programmer_value(f.fid, "intensity", 76)
                    count += 1
            return CommandResult(True, f"Lowlight {count} Fixtures")
        except Exception as e:
            return CommandResult(False, f"Lowlight Fehler: {e}")


@dataclass
class ErrorCommand(Command):
    message: str

    def execute(self, state) -> CommandResult:
        return CommandResult(False, self.message)


# ── Attribut-Mapping ─────────────────────────────────────────────────────────

ATTR_MAP = {
    "intensity": "intensity", "dim": "intensity",
    "r": "color_r", "red": "color_r",
    "g": "color_g", "green": "color_g",
    "b": "color_b", "blue": "color_b",
    "w": "color_w", "white": "color_w",
    "pan": "pan", "tilt": "tilt",
    "zoom": "zoom", "focus": "focus",
    "strobe": "shutter", "shutter": "shutter",
}


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _short_list(fids: list[int], limit: int = 8) -> str:
    if not fids:
        return ""
    if len(fids) <= limit:
        return ",".join(str(x) for x in fids)
    head = ",".join(str(x) for x in fids[:limit])
    return f"{head},...(+{len(fids) - limit})"


# ── Parser ───────────────────────────────────────────────────────────────────

def parse(text: str) -> Command:
    """Parse einen Befehls-String und liefert ein Command-Objekt."""
    try:
        tokens = tokenize(text)
    except Exception as e:
        return ErrorCommand(f"Lexer-Fehler: {e}")

    pos = 0

    def peek() -> Token:
        return tokens[pos] if pos < len(tokens) else tokens[-1]

    def advance() -> Token:
        nonlocal pos
        t = tokens[pos]
        if pos < len(tokens) - 1:
            pos += 1
        return t

    def consume_number():
        t = peek()
        if t.type == TokenType.NUMBER:
            advance()
            try:
                if "." in t.value:
                    return float(t.value)
                return int(t.value)
            except ValueError:
                return None
        return None

    # ── Verben am Anfang ────────────────────────────────────────────────────
    t = peek()
    if t.type == TokenType.KEYWORD:
        kw = t.value
        if kw in ("clear", "cl"):
            advance()
            return ClearCommand()
        if kw in ("blackout", "bo"):
            advance()
            return BlackoutCommand()
        if kw in ("highlight", "hi"):
            advance()
            return HighlightCommand()
        if kw in ("lowlight", "lo"):
            advance()
            return LowlightCommand()
        if kw in ("go", "g"):
            advance()
            n = consume_number()
            # `is not None` statt Falsy-Check: `go 0`/`stop 0` fiel sonst still auf
            # den Default (Slot 1 bzw. Stop-ALL!) statt als ungueltig zu gelten.
            return GoCommand(slot=int(n) if n is not None else 1)
        if kw == "back":
            advance()
            n = consume_number()
            return BackCommand(slot=int(n) if n is not None else 1)
        if kw == "stop":
            advance()
            n = consume_number()
            return StopCommand(slot=int(n) if n is not None else None)
        if kw == "page":
            advance()
            nxt = peek()
            if nxt.type == TokenType.OPERATOR and nxt.value == "+":
                advance()
                return PageCommand(delta=+1)
            if nxt.type == TokenType.OPERATOR and nxt.value == "-":
                advance()
                return PageCommand(delta=-1)
            if nxt.type == TokenType.KEYWORD and nxt.value == "next":
                advance()
                return PageCommand(delta=+1)
            if nxt.type == TokenType.KEYWORD and nxt.value == "prev":
                advance()
                return PageCommand(delta=-1)
            n = consume_number()
            return PageCommand(page=int(n) if n else 1)
        if kw == "record":
            advance()
            sub = peek()
            if sub.type == TokenType.KEYWORD and sub.value == "cue":
                advance()
                n = consume_number()
                return RecordCueCommand(number=float(n) if n is not None else 1.0)
            if sub.type == TokenType.KEYWORD and sub.value == "scene":
                advance()
                nm_t = peek()
                name = ""
                if nm_t.type == TokenType.STRING:
                    name = advance().value
                elif nm_t.type == TokenType.KEYWORD:
                    name = advance().value
                return RecordSceneCommand(name=name)
            return RecordCueCommand()

    # ── Selektion parsen ────────────────────────────────────────────────────
    sel = SelectionExpr()
    if peek().type == TokenType.KEYWORD and peek().value == "all":
        advance()
        sel.all_fixtures = True
    else:
        while True:
            tt = peek()
            if tt.type == TokenType.NUMBER:
                start = int(advance().value)
                if peek().type == TokenType.KEYWORD and peek().value == "thru":
                    advance()
                    nn = consume_number()
                    if nn is not None:
                        sel.ranges.append((start, int(nn)))
                    else:
                        sel.add.append(start)
                else:
                    sel.add.append(start)
            elif tt.type == TokenType.OPERATOR and tt.value == "+":
                advance()
                continue
            elif tt.type == TokenType.OPERATOR and tt.value == "-":
                advance()
                nn = consume_number()
                if nn is not None:
                    sel.excludes.append(int(nn))
            elif tt.type == TokenType.KEYWORD and tt.value == "plus":
                advance()
                continue
            elif tt.type == TokenType.KEYWORD and tt.value == "minus":
                advance()
                nn = consume_number()
                if nn is not None:
                    sel.excludes.append(int(nn))
            else:
                break

    # ── Wert-Teil ───────────────────────────────────────────────────────────
    tt = peek()
    if tt.type == TokenType.OPERATOR and tt.value == "@":
        advance()
        nt = peek()
        if nt.type == TokenType.KEYWORD and nt.value in ("full", "ff"):
            advance()
            return SetValueCommand(sel, "intensity", value_pct=100)
        if nt.type == TokenType.KEYWORD and nt.value == "off":
            advance()
            return SetValueCommand(sel, "intensity", value_pct=0)
        n = consume_number()
        if n is not None:
            return SetValueCommand(sel, "intensity", value_pct=int(n))
        return ErrorCommand("'@' ohne Wert — Beispiel: '1 thru 5 @ 80'")

    # attribute name + number (z.B. "1 thru 5 r 200")
    if tt.type == TokenType.KEYWORD and tt.value in ATTR_MAP:
        attr = ATTR_MAP[advance().value]
        n = consume_number()
        if n is None:
            return ErrorCommand(f"'{attr}' ohne Wert — Beispiel: '1 r 200'")
        return SetValueCommand(sel, attr, value_raw=int(n))

    # Nur Selektion
    if not sel.is_empty():
        return SelectionCommand(sel)

    # Empty / unknown
    raw = (text or "").strip()
    if not raw:
        return ErrorCommand("Leerer Befehl")
    return ErrorCommand(
        f"Unbekannter Befehl: '{raw}'. "
        "Tipp: '1 thru 5 @ 80'  'all @ full'  'go 1'  'page 2'  'clear'"
    )


def execute(text: str, state) -> CommandResult:
    """Hauptentry: parse + execute. Liefert immer ein CommandResult."""
    try:
        cmd = parse(text)
        result = cmd.execute(state)
        if isinstance(result, CommandResult):
            return result
        return CommandResult(True, str(result))
    except Exception as e:
        return CommandResult(False, f"Fehler: {e}")
