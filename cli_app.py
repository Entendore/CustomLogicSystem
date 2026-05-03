# cli_app.py
import cmd
import sys
import logging
from logic_engine import LogicEngine, logger
# FIX: Import helpers from logic_types, not logic_engine
from logic_types import format_term, substitute

# Custom Formatter for Colored Logs
class ColorFormatter(logging.Formatter):
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + "%(message)s" + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + "%(message)s" + reset,
        logging.CRITICAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

class LogicShell(cmd.Cmd):
    intro = "Welcome to the Advanced Logic Programming System. Type 'help'."
    prompt = "Logic> "

    def __init__(self):
        super().__init__()
        self.engine = LogicEngine()
        self.setup_logging()
        self._load_examples()

    def setup_logging(self):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(ColorFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO) 

    def _load_examples(self):
        self.engine.parse("parent(john, mary). parent(mary, susan).")
        self.engine.optimize()

    def do_query(self, arg):
        """Run a query: query parent(john, X)"""
        if not arg: return
        try:
            count = 0
            for res in self.engine.query(arg):
                count += 1
                vars = [k for k in res if k[0].isupper()]
                if vars:
                    print(f"Solution {count}: { {v: format_term(substitute(v, res)) for v in vars} }")
                else:
                    print(f"Solution {count}: True")
            if count == 0:
                print("False.")
        except Exception as e:
            logger.error(f"Query failed: {e}")

    def do_trace(self, arg):
        """Toggle trace: trace on/off"""
        lvl = logging.DEBUG if arg == 'on' else logging.INFO
        logger.setLevel(lvl)
        self.engine.trace_enabled = (arg == 'on')
        print(f"Trace {'enabled' if arg=='on' else 'disabled'}")

    def do_reset(self, arg):
        """Clears the knowledge base."""
        self.engine.clear()
        print("Knowledge base cleared.")

    def default(self, line):
        line = line.strip()
        if not line: return
        
        if line.endswith('.'):
            try:
                self.engine.parse(line)
                self.engine.optimize()
                print("Fact/Rule added.")
            except Exception as e:
                logger.error(f"Syntax Error: {e}")
        elif line.startswith('?-'):
            self.do_query(line[2:].rstrip('.'))
        else:
            print("Unknown command. End facts with '.', or use 'query ...'")

if __name__ == "__main__":
    LogicShell().cmdloop()