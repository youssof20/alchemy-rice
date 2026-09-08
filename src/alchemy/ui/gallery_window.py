from __future__ import annotations

import sys
from typing import Any

from alchemy.services.gallery_service import GalleryService


def run_gallery() -> int:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QApplication,
            QComboBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QMainWindow,
            QPushButton,
            QSplitter,
            QVBoxLayout,
            QWidget,
        )
    except ImportError:
        print("PySide6 is required for the GUI. Install the project dependencies.", file=sys.stderr)
        return 2

    app = QApplication(sys.argv)
    app.setApplicationName("Alchemy")
    service = GalleryService()
    window = QMainWindow()
    window.setWindowTitle("Alchemy — Gallery")
    window.resize(1100, 700)
    root = QWidget()
    layout = QVBoxLayout(root)
    title = QLabel("ALCHEMY / COMMUNITY GALLERY")
    title.setObjectName("title")
    subtitle = QLabel(
        "Cached snapshot · no per-card API calls · use alchemy gallery-refresh to update"
    )
    subtitle.setObjectName("muted")
    subtitle.setTextFormat(Qt.TextFormat.PlainText)
    layout.addWidget(title)
    layout.addWidget(subtitle)

    controls = QHBoxLayout()
    search = QLineEdit()
    search.setPlaceholderText("Search cached entries")
    sort = QComboBox()
    sort.addItems(["Recently Updated", "New", "Most Downloaded", "Community Confirmed"])
    controls.addWidget(search, 1)
    controls.addWidget(sort)
    layout.addLayout(controls)

    splitter = QSplitter(Qt.Orientation.Horizontal)
    listing = QListWidget()
    detail = QLabel("Select a rice to inspect its pinned source and objective badges.")
    detail.setTextFormat(Qt.TextFormat.PlainText)
    detail.setWordWrap(True)
    detail.setAlignment(Qt.AlignmentFlag.AlignTop)
    detail.setMargin(18)
    splitter.addWidget(listing)
    splitter.addWidget(detail)
    splitter.setSizes([380, 720])
    layout.addWidget(splitter, 1)

    report_hint = QPushButton("Reports are previewed with: alchemy gallery-report")
    report_hint.setEnabled(False)
    layout.addWidget(report_hint)

    visible: list[dict[str, Any]] = []

    def populate() -> None:
        nonlocal visible
        mapping = {
            "Recently Updated": "updated",
            "New": "new",
            "Most Downloaded": "downloads",
            "Community Confirmed": "confirmed",
        }
        visible = service.browse(
            query=search.text() or None, sort_by=mapping[sort.currentText()]
        )["entries"]
        listing.clear()
        for entry in visible:
            listing.addItem(f"{entry['name']}  ·  {entry['author']['name']}")
        if not visible:
            detail.setText("No cached entries match. Refresh explicitly from the CLI when online.")

    def show_entry(row: int) -> None:
        if not 0 <= row < len(visible):
            return
        entry = visible[row]
        badges = "\n".join(f"• {badge['label']}" for badge in entry["badges"])
        screenshots = "\n".join(item["url"] for item in entry["screenshots"])
        detail.setText(
            f"{entry['name']}  {entry['version']}\n\n"
            f"{entry['summary']}\n\n"
            f"Source: {entry['source']['repo']}\n"
            f"Release: {entry['source']['release']}\n"
            f"Commit: {entry['source']['commit']}\n\n"
            f"Badges\n{badges}\n\n"
            f"Screenshot references\n{screenshots}"
        )

    search.textChanged.connect(populate)
    sort.currentTextChanged.connect(populate)
    listing.currentRowChanged.connect(show_entry)
    populate()
    if visible:
        listing.setCurrentRow(0)
    window.setCentralWidget(root)
    window.setStyleSheet(_STYLESHEET)
    window.show()
    return app.exec()


_STYLESHEET = """
QWidget { background: #0D0D0D; color: #E0E0E0; font-size: 13px; }
#title { color: #FF3864; font-size: 20px; font-weight: 700; letter-spacing: 2px; }
#muted { color: #8B8B8B; }
QListWidget, QLabel, QLineEdit, QComboBox {
    background: #1A1A1A; border: 1px solid #333333; padding: 8px;
}
QListWidget::item { padding: 10px; }
QListWidget::item:selected { background: #2A1820; color: #FF3864; }
QPushButton { background: #1A1A1A; border: 1px solid #444444; padding: 8px; }
QPushButton:disabled { color: #777777; }
"""
