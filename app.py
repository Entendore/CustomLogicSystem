# app.py
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="Advanced Logic Programming System")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode")
    args = parser.parse_args()

    if args.cli:
        from cli_app import LogicShell
        LogicShell().cmdloop()
    else:
        try:
            from PySide6.QtWidgets import QApplication
            from gui_app import MainWindow
            app = QApplication(sys.argv)
            win = MainWindow()
            win.show()
            sys.exit(app.exec())
        except ImportError:
            print("PySide6 not found. Falling back to CLI. Install with: pip install PySide6")
            from cli_app import LogicShell
            LogicShell().cmdloop()

if __name__ == "__main__":
    main()