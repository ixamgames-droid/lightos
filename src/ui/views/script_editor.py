"""Script Editor - edit a ScriptFunction with syntax-highlighted commands."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QGroupBox,
)
from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
)
from src.core.engine.script_func import ScriptFunction
from src.core.engine.function_manager import get_function_manager


class ScriptHighlighter(QSyntaxHighlighter):
    """Simple syntax highlighter for the LightOS script language."""

    def __init__(self, doc):
        super().__init__(doc)
        self._rules = []

        # Keywords
        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#569CD6"))
        kw_fmt.setFontWeight(QFont.Weight.Bold)
        for kw in ["wait", "setdmx", "setfixture", "start", "stop",
                   "function", "blackout", "on", "off"]:
            self._rules.append((QRegularExpression(rf"\b{kw}\b"), kw_fmt))

        # Numbers
        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#B5CEA8"))
        self._rules.append((QRegularExpression(r"\b\d+(\.\d+)?\b"), num_fmt))

        # Attributes (identifiers after setfixture)
        attr_fmt = QTextCharFormat()
        attr_fmt.setForeground(QColor("#CE9178"))
        self._rules.append((QRegularExpression(r"\b(intensity|pan|tilt|color_r|color_g|color_b|color_w|zoom|gobo|strobe)\b"), attr_fmt))

        # Comments
        self._cmt_fmt = QTextCharFormat()
        self._cmt_fmt.setForeground(QColor("#6A9955"))
        self._cmt_fmt.setFontItalic(True)

    def highlightBlock(self, text: str):
        for regex, fmt in self._rules:
            it = regex.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)
        # Comments
        idx = text.find("#")
        if idx >= 0:
            self.setFormat(idx, len(text) - idx, self._cmt_fmt)


HELP_TEXT = """\
Verfuegbare Befehle (eine pro Zeile):

  wait <sekunden>
    z.B.  wait 2.5

  setdmx <universe> <channel> <value>
    z.B.  setdmx 1 1 255

  setfixture <fid> <attribute> <value>
    Attribute: intensity, pan, tilt,
               color_r/g/b/w, zoom, gobo, ...
    z.B.  setfixture 5 intensity 200

  start function <fid>
    z.B.  start function 7

  stop function <fid>
    z.B.  stop function 7

  blackout on|off

  # Kommentar - eine Zeile mit # ist Kommentar
"""


class ScriptEditor(QWidget):
    def __init__(self, script: ScriptFunction, parent=None):
        super().__init__(parent)
        self._script = script
        self._fm = get_function_manager()
        self._building = False
        self._setup_ui()
        self._load_script()

    def set_script(self, script: ScriptFunction):
        self._script = script
        self._load_script()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Name + run controls
        top = QHBoxLayout()
        top.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._on_name_changed)
        top.addWidget(self._name_edit, 1)

        self._btn_run = QPushButton("Run")
        self._btn_run.clicked.connect(self._run)
        top.addWidget(self._btn_run)

        self._btn_stop = QPushButton("Stop")
        self._btn_stop.clicked.connect(self._stop)
        top.addWidget(self._btn_stop)
        root.addLayout(top)

        # Split: editor left, help right
        body = QHBoxLayout()
        body.setSpacing(8)

        self._editor = QPlainTextEdit()
        self._editor.setFont(QFont("Consolas", 11))
        self._editor.setStyleSheet(
            "QPlainTextEdit { background: #1e1e1e; color: #dcdcdc; }"
        )
        self._highlighter = ScriptHighlighter(self._editor.document())
        self._editor.textChanged.connect(self._on_text_changed)
        body.addWidget(self._editor, 1)

        help_box = QGroupBox("Befehle")
        help_l = QVBoxLayout(help_box)
        help_lbl = QLabel(HELP_TEXT)
        help_lbl.setFont(QFont("Consolas", 9))
        help_lbl.setStyleSheet("color: #cccccc;")
        help_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        help_l.addWidget(help_lbl)
        help_l.addStretch(1)
        help_box.setMaximumWidth(280)
        body.addWidget(help_box)

        root.addLayout(body, 1)

    def _load_script(self):
        self._building = True
        self._name_edit.setText(self._script.name)
        self._editor.setPlainText(self._script.script)
        self._building = False

    def _on_name_changed(self, txt: str):
        if not self._building:
            self._script.name = txt

    def _on_text_changed(self):
        if not self._building:
            self._script.script = self._editor.toPlainText()

    def _run(self):
        try:
            self._fm.start(self._script.id)
        except Exception as e:
            print(f"[ScriptEditor] Run error: {e}")

    def _stop(self):
        try:
            self._fm.stop(self._script.id)
        except Exception as e:
            print(f"[ScriptEditor] Stop error: {e}")
