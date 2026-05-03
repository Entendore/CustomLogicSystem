# gui_app.py
import sys
import logging
import io
import os
import contextlib
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QTextEdit, QPushButton, QLineEdit, 
                               QLabel, QTabWidget, QTableWidget, QTableWidgetItem, 
                               QMessageBox, QFileDialog)
from PySide6.QtCore import QThread, Signal, QObject, Slot
from PySide6.QtGui import QColor, QTextCharFormat, QSyntaxHighlighter, QTextDocument

from logic_engine import LogicEngine, logger
from logic_types import format_term, substitute

# --- Basic Syntax Highlighter ---
class PrologHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(QColor("darkBlue"))
        self.keyword_format.setFontWeight(75)
        self.keywords = [":-", "?-", "%", "->", "-->"]

    def highlightBlock(self, text):
        for kw in self.keywords:
            start = text.find(kw)
            while start >= 0:
                self.setFormat(start, len(kw), self.keyword_format)
                start = text.find(kw, start + len(kw))
        if text.strip().startswith("%"):
            comment_format = QTextCharFormat()
            comment_format.setForeground(QColor("gray"))
            self.setFormat(0, len(text), comment_format)

# --- Qt Logging Handler ---
class QtLogHandler(QObject, logging.Handler):
    log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        
    def emit(self, record):
        msg = self.format(record)
        self.log_signal.emit(msg)

# --- Worker Thread ---
class QueryWorker(QObject):
    finished = Signal()
    error = Signal(str)
    solution = Signal(dict)

    def __init__(self, engine, query):
        super().__init__()
        self.engine = engine
        self.query = query

    @Slot()
    def run(self):
        try:
            for res in self.engine.query(self.query):
                self.solution.emit(res)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

# --- Main Window ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Logic Engine GUI")
        self.resize(900, 700)
        
        self.engine = LogicEngine()
        self.worker = None
        self.worker_thread = None
        
        self.setup_ui()
        self.setup_logging()
        self.load_examples()

    def setup_logging(self):
        # Clear existing handlers to avoid duplicates or invalid handles
        logger.handlers.clear()
        
        # 1. Console Handler (Safe check for stdout)
        if sys.stdout and hasattr(sys.stdout, 'write'):
            try:
                ch = logging.StreamHandler(sys.stdout)
                ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
                logger.addHandler(ch)
            except Exception:
                pass # Ignore if stdout is invalid

        # 2. Qt GUI Handler
        self.qt_handler = QtLogHandler()
        self.qt_handler.log_signal.connect(self.append_log)
        self.qt_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s', "%H:%M:%S"))
        logger.addHandler(self.qt_handler)
        
        logger.setLevel(logging.INFO)

    @Slot(str)
    def append_log(self, msg):
        self.log_output.append(msg)
        sb = self.log_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def setup_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        lay = QVBoxLayout(w)

        lay.addWidget(QLabel("Code Editor:"))
        self.editor = QTextEdit()
        self.highlighter = PrologHighlighter(self.editor.document())
        self.editor.setPlaceholderText("Enter Prolog code here...")
        lay.addWidget(self.editor)

        btn_lay = QHBoxLayout()
        btn_update = QPushButton("Update KB")
        btn_update.clicked.connect(self.update_kb)
        
        btn_load = QPushButton("Load File")
        btn_load.clicked.connect(self.load_file_dialog)
        
        btn_save = QPushButton("Save File")
        btn_save.clicked.connect(self.save_file_dialog)
        
        btn_lay.addWidget(btn_update)
        btn_lay.addWidget(btn_load)
        btn_lay.addWidget(btn_save)
        lay.addLayout(btn_lay)

        self.query_inp = QLineEdit()
        self.query_inp.setPlaceholderText("?- query.")
        self.query_inp.returnPressed.connect(self.run_query)
        btn_run = QPushButton("Run Query")
        btn_run.clicked.connect(self.run_query)
        
        q_lay = QHBoxLayout()
        q_lay.addWidget(self.query_inp)
        q_lay.addWidget(btn_run)
        lay.addLayout(q_lay)

        tabs = QTabWidget()
        
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(1)
        self.results_table.setHorizontalHeaderLabels(["Result"])
        tabs.addTab(self.results_table, "Solutions")
        
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        tabs.addTab(self.log_output, "Engine Log")
        
        test_widget = QWidget()
        test_layout = QVBoxLayout(test_widget)
        
        self.test_output = QTextEdit()
        self.test_output.setReadOnly(True)
        self.test_output.setFontFamily("Courier")
        
        btn_run_tests = QPushButton("Run All Unit Tests")
        btn_run_tests.clicked.connect(self.run_tests)
        
        test_layout.addWidget(btn_run_tests)
        test_layout.addWidget(self.test_output)
        tabs.addTab(test_widget, "Unit Tests")
        
        lay.addWidget(tabs)

    def run_tests(self):
        self.test_output.clear()
        self.test_output.append("Starting Pytest Discovery...\n")
        
        # Check if pytest is available
        try:
            import pytest
        except ImportError:
            self.test_output.append("<font color='red'>Error: pytest is not installed.</font>\n")
            self.test_output.append("Please install it using: pip install pytest")
            return

        # Capture stdout/stderr to a buffer to avoid WinError 6
        # and to display results in the GUI.
        buffer = io.StringIO()
        
        # We need to temporarily redirect stdout/stderr for the pytest run
        # to capture prints and logging output that goes to console.
        try:
            # Use contextlib to safely redirect streams
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                # Run pytest programmatically
                # -v: verbose
                exit_code = pytest.main(["-v", "tests/"])
        except Exception as e:
            buffer.write(f"\n<font color='red'>Error running tests: {e}</font>\n")
            # If pytest crashes hard, we still want to show the error
            import traceback
            traceback.print_exc(file=buffer)
            
        # Display output
        output_text = buffer.getvalue()
        self.test_output.append(output_text)
        
        self.test_output.append("\n" + "="*30)
        if exit_code == 0:
            self.test_output.append("<font color='green'>All Tests Passed!</font>")
        else:
            self.test_output.append(f"<font color='red'>Tests Failed (Exit Code: {exit_code}).</font>")

    def load_file_dialog(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Open Logic File", "", "Prolog Files (*.pl *.pro);;All Files (*)")
        if fname:
            try:
                with open(fname, 'r') as f:
                    self.editor.setText(f.read())
                QMessageBox.information(self, "Loaded", "File loaded.")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def save_file_dialog(self):
        fname, _ = QFileDialog.getSaveFileName(self, "Save Logic File", "", "Prolog Files (*.pl);;All Files (*)")
        if fname:
            try:
                with open(fname, 'w') as f:
                    f.write(self.editor.toPlainText())
                QMessageBox.information(self, "Saved", "File saved successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def update_kb(self):
        code = self.editor.toPlainText()
        try:
            self.engine.clear()
            self.engine.parse(code)
            self.engine.optimize()
            self.results_table.setRowCount(0)
            self.log_output.clear()
            logger.info("Knowledge Base Updated Successfully.")
        except Exception as e:
            logger.error(f"KB Update Failed: {e}")

    def run_query(self):
        q = self.query_inp.text().strip().lstrip('?-').rstrip('.')
        if not q: return
        
        self.results_table.setRowCount(0)
        
        self.worker = QueryWorker(self.engine, q)
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        
        self.worker.solution.connect(self.add_solution)
        self.worker.error.connect(lambda e: logger.error(f"Query Error: {e}"))
        self.worker.finished.connect(self.cleanup_thread)
        self.worker_thread.started.connect(self.worker.run)
        
        self.worker_thread.start()

    def add_solution(self, sol):
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)
        text = ", ".join(f"{k}={format_term(substitute(k, sol))}" for k in sol if k[0].isupper())
        self.results_table.setItem(row, 0, QTableWidgetItem(text))

    def cleanup_thread(self):
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker_thread = None
            self.worker = None

    def load_examples(self):
        code = """% Family Relationships
parent(john, mary).
parent(john, tom).
parent(mary, ann).

ancestor(X, Y) :- parent(X, Y).
ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).

% List Utils
append([], L, L).
append([H|T], L, [H|R]) :- append(T, L, R).
"""
        self.editor.setText(code)
        self.update_kb()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())