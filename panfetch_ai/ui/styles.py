from __future__ import annotations


APP_STYLE = """
QMainWindow, QDialog { background: #10151C; color: #EDF2F7; }
QWidget {
    color: #DDE6EE;
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 13px;
    letter-spacing: 0px;
}
QToolBar {
    background: #141B23;
    border: 0;
    border-bottom: 1px solid #2B3744;
    spacing: 6px;
    padding: 8px 12px;
}
QLabel#brandLabel { color: #F7FAFC; font-size: 18px; font-weight: 700; }
QLabel[sectionTitle="true"] { color: #F3F7FA; font-size: 15px; font-weight: 700; }
QLabel[panelTitle="true"] { color: #F7FAFC; font-size: 17px; font-weight: 700; }
QWidget#homePage { background: #10151C; }
QWidget#planPage { background: #10151C; }
QWidget#operationPage { background: #10151C; }
QFrame#historyRail {
    background: #131A22;
    border: 0;
    border-right: 1px solid #2B3744;
    padding-right: 6px;
}
QFrame#chatSurface { background: #10151C; border: 0; }
QFrame#tracePanel {
    background: #121A20;
    border: 0;
    border-left: 1px solid #2F4850;
    padding-left: 6px;
}
QLabel#homeTitle { color: #F7FAFC; font-size: 24px; font-weight: 700; }
QLabel#planTitle { color: #F7FAFC; font-size: 24px; font-weight: 700; }
QLabel#operationTitle { color: #F7FAFC; font-size: 24px; font-weight: 700; }
QLabel#operationBackend {
    background: #132127;
    border: 1px solid #2B626D;
    border-left: 3px solid #28C3D6;
    border-radius: 5px;
    padding: 10px 12px;
}
QLabel#operationBackend[state="error"] {
    background: #241A1D;
    border-color: #704148;
    border-left-color: #F08B84;
    color: #F3B0AB;
}
QFrame#planSummaryBand {
    background: #132127;
    border: 1px solid #2B626D;
    border-left: 3px solid #28C3D6;
    border-radius: 5px;
    padding: 7px 10px;
}
QWidget#accountRail { background: #131A22; }
QWidget#workspacePanel { background: #10151C; }
QWidget#assistantPanel { background: #121820; }
QToolButton, QPushButton {
    min-height: 30px;
    padding: 0 11px;
    border: 1px solid #364554;
    border-radius: 5px;
    background: #1B242E;
    color: #DDE6EE;
}
QToolButton:hover, QPushButton:hover { border-color: #28C3D6; background: #202D38; color: #FFFFFF; }
QToolButton:pressed, QPushButton:pressed { background: #263644; }
QPushButton:disabled { background: #171E27; border-color: #27333E; color: #647382; }
QPushButton[primary="true"] {
    background: #247FA5;
    border-color: #2AA8C2;
    color: #FFFFFF;
    font-weight: 600;
}
QPushButton[primary="true"]:hover { background: #2A91B8; border-color: #49CAD8; }
QPushButton[danger="true"] { color: #F0A09B; border-color: #704148; background: #211B21; }
QPushButton[nav="true"] {
    min-width: 86px;
    background: transparent;
    border: 0;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    color: #8D9AA8;
    font-weight: 600;
}
QPushButton[nav="true"]:hover { background: #18222C; color: #E9F3F7; }
QPushButton[nav="true"][active="true"] {
    color: #72DCE5;
    border-bottom: 2px solid #28C3D6;
}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {
    background: #151D26;
    border: 1px solid #344250;
    border-radius: 5px;
    padding: 6px 8px;
    color: #E8EEF4;
    selection-background-color: #247FA5;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #28C3D6; }
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled { background: #121820; color: #6F7D89; }
QTreeWidget, QTableWidget, QListWidget {
    background: #141B23;
    border: 1px solid #2B3744;
    border-radius: 5px;
    alternate-background-color: #171F28;
    gridline-color: #27333E;
    color: #DDE6EE;
}
QHeaderView::section {
    background: #1D2731;
    color: #AAB7C4;
    border: 0;
    border-right: 1px solid #2B3744;
    border-bottom: 1px solid #2B3744;
    padding: 8px;
    font-weight: 600;
}
QTreeWidget::item, QTableWidget::item { min-height: 30px; }
QTreeWidget::item:selected, QTableWidget::item:selected { background: #1D5165; color: #FFFFFF; }
QListWidget::item {
    min-height: 42px;
    padding: 7px 8px;
    margin: 1px 0;
    border-left: 2px solid transparent;
}
QListWidget::item:hover { background: #1A252F; color: #F3F7FA; }
QListWidget::item:selected {
    background: #172A32;
    color: #EAF9FA;
    border-left: 2px solid #28C3D6;
}
QGroupBox {
    background: #171F28;
    border: 1px solid #2B3744;
    border-radius: 6px;
    margin-top: 16px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #B9C6D2; }
QGroupBox#accountCard { background: #18212B; }
QGroupBox#planPreview { background: #151F27; border-color: #276577; }
QTabWidget::pane { border: 1px solid #2B3744; background: #141B23; border-radius: 5px; }
QTabBar::tab {
    min-width: 92px;
    padding: 9px 14px;
    background: #171F28;
    color: #8392A0;
    border: 0;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    background: #141B23;
    color: #EAF7F8;
    border-bottom: 2px solid #28C3D6;
    font-weight: 600;
}
QProgressBar {
    border: 1px solid #344250;
    border-radius: 4px;
    background: #111820;
    color: #DDE6EE;
    text-align: center;
    min-height: 18px;
}
QProgressBar::chunk { background: #37C78B; border-radius: 3px; }
QLabel#assistantSteps {
    background: #13252B;
    border: 1px solid #255866;
    border-radius: 5px;
    padding: 9px;
    color: #8DE0E6;
    font-weight: 600;
}
QPlainTextEdit#assistantHistory { background: #121920; border-left: 2px solid #247FA5; }
QPlainTextEdit#homeConversation {
    background: #111820;
    border: 0;
    border-top: 1px solid #2B3744;
    border-bottom: 1px solid #2B3744;
    border-radius: 0;
    padding: 14px 12px;
    color: #E9EFF4;
    font-size: 14px;
}
QPlainTextEdit#thinkingStream {
    background: #1D1B17;
    border: 1px solid #514630;
    border-left: 3px solid #C89A4B;
    color: #E6C98F;
    padding: 8px 10px;
}
QFrame#tracePanel QPlainTextEdit {
    background: #111A1C;
    border-color: #2D4B49;
    color: #8FD1BC;
}
QLabel[muted="true"] { color: #8D9AA8; }
QLabel[state="success"] { color: #55D69A; font-weight: 600; }
QLabel[state="error"] { color: #F08B84; font-weight: 600; }
QLabel[status="connected"] { color: #55D69A; font-weight: 600; }
QLabel[status="error"] { color: #F08B84; font-weight: 600; }
QStatusBar { background: #121820; border-top: 1px solid #2B3744; }
QWidget#taskDock { background: #121820; }
QSplitter::handle { background: #2B3744; width: 1px; }
QScrollBar:vertical { background: #121820; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #344554; min-height: 28px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #202A34; color: #EDF2F7; border: 1px solid #3A4A58; padding: 5px; }
"""
