from __future__ import annotations

import json
import sys
from typing import Any

from alchemy.services.environment_probe import EnvironmentProbe


def run_gui() -> int:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QApplication,
            QFrame,
            QHBoxLayout,
            QLabel,
            QListWidget,
            QMainWindow,
            QPushButton,
            QSplitter,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
    except ImportError:
        print("PySide6 is required for the GUI. Install the project dependencies.", file=sys.stderr)
        return 2

    app = QApplication(sys.argv)
    app.setApplicationName("Alchemy")
    app.setStyleSheet(_STYLESHEET)

    report = EnvironmentProbe().inspect()
    payload = report.to_dict()
    window = QMainWindow()
    window.setWindowTitle("Alchemy — Read-only Inspector")
    window.resize(1180, 720)

    root = QWidget()
    root_layout = QVBoxLayout(root)
    title = QLabel("ALCHEMY / SYSTEM INSPECTOR")
    title.setObjectName("title")
    subtitle = QLabel("Phase 7 · Inspector with capture, dependency, and gallery workflows")
    subtitle.setObjectName("muted")
    root_layout.addWidget(title)
    root_layout.addWidget(subtitle)

    splitter = QSplitter(Qt.Orientation.Horizontal)
    components = QListWidget()
    components.addItems(
        [
            "Environment",
            "Colors",
            "Icons",
            "Cursor",
            "Fonts",
            "Plasma theme",
            "Wallpaper",
            "Application style",
            "Window decoration",
            "KWin",
        ]
    )
    components.setCurrentRow(0)
    splitter.addWidget(components)

    table = QTableWidget(0, 2)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setHorizontalHeaderLabels(["Capability", "Observed value"])
    table.horizontalHeader().setStretchLastSection(True)
    for key, value in payload["capabilities"].items():
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(key.replace("_", " ").title()))
        table.setItem(row, 1, QTableWidgetItem(_format_value(value)))
    splitter.addWidget(table)

    detail_frame = QFrame()
    detail_layout = QVBoxLayout(detail_frame)
    detail_layout.addWidget(QLabel("PROPERTIES"))
    details = QLabel("Select a component to inspect its source and observed value.")
    details.setWordWrap(True)
    details.setObjectName("muted")
    detail_layout.addWidget(details)
    detail_layout.addStretch()
    splitter.addWidget(detail_frame)
    splitter.setSizes([210, 650, 280])
    root_layout.addWidget(splitter, 1)

    controls = QHBoxLayout()
    if payload["capabilities"]["apply_supported"]:
        status_text = "Reviewed setting writers are available through the CLI."
    else:
        status_text = "Apply is disabled: this environment did not pass capability checks."
    status = QLabel(status_text)
    status.setObjectName("warning")
    controls.addWidget(status)
    controls.addStretch()
    for label in ("Preview Plan", "Apply", "Revert", "Snapshot", "Export"):
        button = QPushButton(label)
        button.setEnabled(False)
        controls.addWidget(button)
    root_layout.addLayout(controls)

    def show_component(name: str) -> None:
        normalized = name.lower().replace(" ", "_")
        observations = [
            setting for setting in payload["settings"] if setting["component"] == normalized
        ]
        if name == "Environment":
            details.setText("Immutable capability snapshot generated at launch.")
        elif observations:
            lines = [
                f"{item['label']}: {_format_value(item['value'])}\nSource: {item['source']}"
                for item in observations
            ]
            details.setText("\n\n".join(lines))
        else:
            details.setText("No reviewed reader is available for this component yet.")

    components.currentTextChanged.connect(show_component)
    window.setCentralWidget(root)
    window.show()
    return app.exec()


def _format_value(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return str(value)


_STYLESHEET = """
QWidget {
    background: #0D0D0D;
    color: #E0E0E0;
    font-family: Inter, sans-serif;
    font-size: 13px;
}
#title {
    color: #FF3864;
    font-family: "Space Grotesk", sans-serif;
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 2px;
}
#muted { color: #8B8B8B; }
#warning { color: #FFAA00; }
QListWidget, QTableWidget, QFrame {
    background: #1A1A1A;
    border: 1px solid #333333;
    border-radius: 2px;
}
QListWidget::item { padding: 10px; }
QListWidget::item:selected { background: #2A1820; color: #FF3864; }
QHeaderView::section {
    background: #171717;
    color: #777777;
    border: 0;
    border-bottom: 1px solid #333333;
    padding: 7px;
}
QPushButton {
    background: #1A1A1A;
    border: 1px solid #444444;
    border-radius: 2px;
    padding: 7px 12px;
}
QPushButton:disabled { color: #555555; }
"""
