"""QXF Import Dialog — bulk-imports QLC+ fixture files with progress."""
from __future__ import annotations
import os
import threading
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                                QLabel, QProgressBar, QFileDialog, QPlainTextEdit,
                                QLineEdit, QDialogButtonBox)
from PySide6.QtCore import Qt, Signal, QObject


class _Worker(QObject):
    progress = Signal(int, int, int)   # current, total, ok
    finished = Signal(int, int)        # ok, err

    def __init__(self, qxf_dir: str):
        super().__init__()
        self._dir = qxf_dir

    def run(self):
        from src.core.database.qxf_import import import_all_qxf
        ok, err = import_all_qxf(self._dir, progress_cb=self._cb)
        self.finished.emit(ok, err)

    def _cb(self, current: int, total: int, ok: int):
        self.progress.emit(current, total, ok)


class QxfImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QLC+ Fixture-Datenbank importieren")
        self.setMinimumWidth(500)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Directory selection
        dir_row = QHBoxLayout()
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("Verzeichnis mit .qxf Dateien...")
        self._dir_edit.setReadOnly(True)

        # Auto-detect qlcplus-src directory
        default_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "qlcplus-src", "qlcplus-master", "resources", "fixtures"
        )
        default_dir = os.path.normpath(default_dir)
        if os.path.isdir(default_dir):
            self._dir_edit.setText(default_dir)

        btn_browse = QPushButton("Durchsuchen...")
        btn_browse.setFixedWidth(120)
        btn_browse.clicked.connect(self._browse)
        dir_row.addWidget(self._dir_edit)
        dir_row.addWidget(btn_browse)
        layout.addLayout(dir_row)

        # Info label
        self._info_label = QLabel("Bereit. Klicken Sie auf 'Importieren' um zu starten.")
        self._info_label.setStyleSheet("color:#8b949e; font-size:10px;")
        layout.addWidget(self._info_label)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setStyleSheet("""
            QProgressBar { background:#21262d; border:1px solid #30363d; border-radius:3px;
                           color:#e6edf3; font-size:10px; text-align:center; }
            QProgressBar::chunk { background:#1f6feb; border-radius:3px; }
        """)
        layout.addWidget(self._progress)

        # Log output
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        self._log.setMaximumHeight(120)
        self._log.setStyleSheet("""
            QPlainTextEdit { background:#0d1117; color:#8b949e; border:1px solid #21262d;
                             font-size:9px; font-family:Consolas,monospace; }
        """)
        layout.addWidget(self._log)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_import = QPushButton("Importieren")
        self._btn_import.setFixedHeight(30)
        self._btn_import.setStyleSheet("""
            QPushButton { background:#1f6feb; color:#ffffff; border:none;
                          border-radius:3px; font-size:11px; font-weight:bold; }
            QPushButton:hover { background:#388bfd; }
            QPushButton:disabled { background:#21262d; color:#484f58; }
        """)
        self._btn_import.clicked.connect(self._start_import)
        btn_row.addWidget(self._btn_import)

        btn_close = QPushButton("Schließen")
        btn_close.setFixedHeight(30)
        btn_close.setStyleSheet("""
            QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                          border-radius:3px; font-size:11px; }
            QPushButton:hover { background:#30363d; }
        """)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._worker: _Worker | None = None
        self._thread: threading.Thread | None = None

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "QXF Verzeichnis wählen", "")
        if path:
            self._dir_edit.setText(path)

    def _start_import(self):
        qxf_dir = self._dir_edit.text()
        if not qxf_dir or not os.path.isdir(qxf_dir):
            self._log.appendPlainText("Fehler: Ungültiges Verzeichnis.")
            return

        self._btn_import.setEnabled(False)
        self._log.clear()
        self._progress.setValue(0)
        self._info_label.setText("Importiere...")

        self._worker = _Worker(qxf_dir)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)

        self._thread = threading.Thread(target=self._worker.run, daemon=True)
        self._thread.start()

    def _on_progress(self, current: int, total: int, ok: int):
        if total > 0:
            pct = int(current / total * 100)
            self._progress.setValue(pct)
            self._info_label.setText(f"Verarbeite {current}/{total} Dateien — {ok} importiert...")
            if current % 50 == 0:
                self._log.appendPlainText(f"  {current}/{total} — {ok} OK")

    def _on_finished(self, ok: int, err: int):
        self._progress.setValue(100)
        self._info_label.setText(f"Fertig! {ok} Fixtures importiert, {err} Fehler.")
        self._log.appendPlainText(f"\n✓ Import abgeschlossen: {ok} Fixtures, {err} Fehler")
        self._btn_import.setEnabled(True)
