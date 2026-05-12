# main.py
import argparse
import sys
import os

def main():
    parser = argparse.ArgumentParser(description="Advanced Logic Programming System")
    parser.add_argument("--mode", "-m", choices=["streamlit", "cli"], default="cli", 
                        help="Choose the interface mode (default: cli)")
    
    args, remaining = parser.parse_known_args()
    
    if args.mode == "streamlit":
        # Import and run the Streamlit app
        import streamlit.web.cli as stcli
        sys.argv = ["streamlit", "run", "streamlit_app.py"] + remaining
        stcli.main()
    else:
        # Import and run the CLI
        from CustomLogicSystem.old.cli_app import cli_mode
        sys.argv = ["logic_system"] + remaining
        cli_mode()

if __name__ == "__main__":
    main()