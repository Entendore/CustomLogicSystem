# cli_app.py
import argparse
import sys
import os
import cmd
import shlex
import time
import re
from datetime import datetime

# Import the logic engine
from logic_engine import LogicEngine, format_term, substitute

class LogicShell(cmd.Cmd):
    """Command-line interface for the Logic Programming System."""
    
    intro = "Welcome to the Advanced Logic Programming System. Type 'help' for available commands."
    prompt = "Logic> "
    
    def __init__(self, engine=None):
        super().__init__()
        self.engine = engine if engine else LogicEngine()
        self.last_query_time = 0
        self.last_query_solutions = 0
        
        # Load default examples
        self._load_examples()
    
    def _load_examples(self):
        """Load example knowledge base."""
        examples = """
        % Family relationships
        parent(john, mary).
        parent(mary, susan).
        parent(john, mark).
        parent(mark, alice).
        parent(susan, bob).
        
        male(john).
        male(mark).
        male(bob).
        female(mary).
        female(susan).
        female(alice).
        
        % Recursive rules (good for tabling)
        ancestor(X, Y) :- parent(X, Y).
        ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).
        
        % Derived relationships
        father(X, Y) :- parent(X, Y), male(X).
        mother(X, Y) :- parent(X, Y), female(X).
        grandparent(X, Y) :- parent(X, Z), parent(Z, Y).
        
        % List operations
        member(X, [X|_]).
        member(X, [_|T]) :- member(X, T).
        
        append([], L, L).
        append([H|T], L, [H|R]) :- append(T, L, R).
        
        length([], 0).
        length([_|T], N) :- length(T, M), N is M + 1.
        
        % DCG Example
        sentence --> noun_phrase, verb_phrase.
        noun_phrase --> determiner, noun.
        verb_phrase --> verb.
        determiner --> [the].
        noun --> [cat]. noun --> [dog].
        verb --> [sleeps]. verb --> [runs].
        
        % Constraint Example
        magic_square([[A,B,C],[D,E,F],[G,H,I]]) :-
            [A,B,C,D,E,F,G,H,I] ins 1..9,
            all_different([A,B,C,D,E,F,G,H,I]),
            A+B+C #= 15, D+E+F #= 15, G+H+I #= 15,
            A+D+G #= 15, B+E+H #= 15, C+F+I #= 15,
            A+E+I #= 15, C+E+G #= 15.
        """
        
        self.engine.parse(examples, "examples")
        self.engine.optimize()
        print("Loaded example knowledge base.")
    
    def do_load(self, arg):
        """Load a logic file: load <filename>"""
        if not arg:
            print("Error: Please specify a filename.")
            return
        
        try:
            with open(arg, 'r') as f:
                content = f.read()
            self.engine.parse(content, arg)
            self.engine.optimize()
            print(f"Loaded {arg} successfully.")
        except Exception as e:
            print(f"Error loading {arg}: {e}")
    
    def do_save(self, arg):
        """Save the current knowledge base to a file: save <filename>"""
        if not arg:
            print("Error: Please specify a filename.")
            return
        
        try:
            with open(arg, 'w') as f:
                # Write facts
                for pred, facts in self.engine.facts.items():
                    for fact in facts:
                        args_str = ', '.join([format_term(arg) for arg in fact])
                        f.write(f"{pred}({args_str}).\n")
                
                # Write rules
                for rule in self.engine.rules:
                    head_name, head_args, body_parts = rule
                    head_str = f"{head_name}({', '.join([format_term(arg) for arg in head_args])})"
                    body_str = ', '.join([f"{name}({', '.join([format_term(arg) for arg in args])})" for name, args in body_parts])
                    f.write(f"{head_str} :- {body_str}.\n")
            
            print(f"Saved knowledge base to {arg}.")
        except Exception as e:
            print(f"Error saving to {arg}: {e}")
    
    def do_clear(self, arg):
        """Clear the knowledge base: clear"""
        self.engine.clear()
        print("Knowledge base cleared.")
    
    def do_query(self, arg):
        """Execute a query: query <query>"""
        if not arg:
            print("Error: Please specify a query.")
            return
        
        try:
            start_time = time.time()
            solutions = []
            
            for solution in self.engine.query(arg):
                solutions.append(solution)
            
            duration = time.time() - start_time
            self.last_query_time = duration
            self.last_query_solutions = len(solutions)
            
            # Extract variable names from the query
            var_names = list(set(re.findall(r'\b[A-Z]\w*\b', arg)))
            
            if solutions:
                print(f"Found {len(solutions)} solutions in {duration:.3f}s:")
                
                if var_names:
                    for i, solution in enumerate(solutions):
                        print(f"Solution {i+1}:")
                        for var in var_names:
                            if var in solution:
                                print(f"  {var} = {format_term(substitute(var, solution))}")
                else:
                    print("Yes")
            else:
                print("No solutions found.")
        except Exception as e:
            print(f"Error executing query: {e}")
    
    def do_consult(self, arg):
        """Consult a file (alternative to load): consult <filename>"""
        self.do_load(arg)
    
    def do_list(self, arg):
        """List the current knowledge base: list [facts|rules|all]"""
        if not arg or arg == "all":
            self._list_facts()
            self._list_rules()
        elif arg == "facts":
            self._list_facts()
        elif arg == "rules":
            self._list_rules()
        else:
            print("Error: Invalid argument. Use 'facts', 'rules', or 'all'.")
    
    def _list_facts(self):
        """List all facts in the knowledge base."""
        print("Facts:")
        for pred, facts in self.engine.facts.items():
            for fact in facts:
                args_str = ", ".join([format_term(arg) for arg in fact])
                print(f"  {pred}({args_str}).")
    
    def _list_rules(self):
        """List all rules in the knowledge base."""
        print("Rules:")
        for rule in self.engine.rules:
            head_name, head_args, body_parts = rule
            head_str = f"{head_name}({', '.join([format_term(arg) for arg in head_args])})"
            body_str = ", ".join([f"{name}({', '.join([format_term(arg) for arg in args])})" for name, args in body_parts])
            print(f"  {head_str} :- {body_str}.")
    
    def do_table(self, arg):
        """Enable tabling for a predicate: table <predicate/arity>"""
        if not arg:
            print("Error: Please specify a predicate (e.g., ancestor/2).")
            return
        
        self.engine.tabled_predicates.add(arg)
        print(f"Enabled tabling for {arg}.")
    
    def do_untable(self, arg):
        """Disable tabling for a predicate: untable <predicate/arity>"""
        if not arg:
            print("Error: Please specify a predicate (e.g., ancestor/2).")
            return
        
        if arg in self.engine.tabled_predicates:
            self.engine.tabled_predicates.remove(arg)
            print(f"Disabled tabling for {arg}.")
        else:
            print(f"{arg} is not currently tabled.")
    
    def do_list_tabled(self, arg):
        """List all tabled predicates: list_tabled"""
        if self.engine.tabled_predicates:
            print("Tabled predicates:")
            for pred in self.engine.tabled_predicates:
                print(f"  {pred}")
        else:
            print("No predicates are currently tabled.")
    
    def do_debug(self, arg):
        """Enable/disable debugging: debug [on|off]"""
        if not arg:
            print(f"Debugging is currently {'enabled' if self.engine.debugger_active else 'disabled'}.")
            return
        
        if arg.lower() == "on":
            self.engine.debugger_active = True
            print("Debugging enabled.")
        elif arg.lower() == "off":
            self.engine.debugger_active = False
            print("Debugging disabled.")
        else:
            print("Error: Invalid argument. Use 'on' or 'off'.")
    
    def do_break(self, arg):
        """Set a breakpoint: break <predicate/arity>"""
        if not arg:
            print("Error: Please specify a predicate (e.g., ancestor/2).")
            return
        
        self.engine.debugger_set_breakpoint(arg)
    
    def do_nobreak(self, arg):
        """Clear a breakpoint: nobreak <predicate/arity>"""
        if not arg:
            print("Error: Please specify a predicate (e.g., ancestor/2).")
            return
        
        self.engine.debugger_clear_breakpoint(arg)
    
    def do_list_breakpoints(self, arg):
        """List all breakpoints: list_breakpoints"""
        if self.engine.breakpoints:
            print("Breakpoints:")
            for bp in self.engine.breakpoints:
                print(f"  {bp}")
        else:
            print("No breakpoints set.")
    
    def do_parallel(self, arg):
        """Enable/disable parallel execution: parallel [on|off]"""
        if not arg:
            print(f"Parallel execution is currently {'enabled' if self.engine.parallel_enabled else 'disabled'}.")
            return
        
        if arg.lower() == "on":
            self.engine.parallel_enabled = True
            print("Parallel execution enabled.")
        elif arg.lower() == "off":
            self.engine.parallel_enabled = False
            print("Parallel execution disabled.")
        else:
            print("Error: Invalid argument. Use 'on' or 'off'.")
    
    def do_trace(self, arg):
        """Enable/disable tracing: trace [on|off]"""
        if not arg:
            print(f"Tracing is currently {'enabled' if self.engine.trace_enabled else 'disabled'}.")
            return
        
        if arg.lower() == "on":
            self.engine.trace_enabled = True
            print("Tracing enabled.")
        elif arg.lower() == "off":
            self.engine.trace_enabled = False
            print("Tracing disabled.")
        else:
            print("Error: Invalid argument. Use 'on' or 'off'.")
    
    def do_stats(self, arg):
        """Show statistics: stats"""
        stats = self.engine.stats()
        print(f"Statistics:")
        print(f"  Facts: {stats['total_facts']}")
        print(f"  Rules: {stats['total_rules']}")
        print(f"  Queries executed: {stats['queries_executed']}")
        print(f"  Resolutions performed: {stats['resolutions_performed']}")
        if self.last_query_solutions > 0:
            print(f"  Last query: {self.last_query_solutions} solutions in {self.last_query_time:.3f}s")
    
    def do_register_foreign(self, arg):
        """Register a foreign function: register_foreign <name/arity> <python_code>"""
        if not arg:
            print("Error: Please specify a predicate and Python code.")
            return
        
        parts = arg.split(maxsplit=1)
        if len(parts) != 2:
            print("Error: Invalid format. Use 'register_foreign <name/arity> <python_code>'.")
            return
        
        pred_sig, python_code = parts
        try:
            # Execute the code to define the function
            exec(python_code, globals())
            # Get the function name from the predicate signature
            func_name = pred_sig.split('/')[0]
            # Get the function object
            func = globals()[func_name]
            # Register it
            self.engine.register_foreign(pred_sig, func)
            print(f"Registered {pred_sig}.")
        except Exception as e:
            print(f"Error registering foreign function: {e}")
    
    def do_list_foreign(self, arg):
        """List all registered foreign functions: list_foreign"""
        if self.engine.foreign_functions:
            print("Registered foreign functions:")
            for (name, arity), func in self.engine.foreign_functions.items():
                print(f"  {name}/{arity}: {func.__name__}")
        else:
            print("No foreign functions registered.")
    
    def do_optimize(self, arg):
        """Optimize the knowledge base: optimize"""
        self.engine.optimize()
        print("Knowledge base optimized.")
    
    def do_validate(self, arg):
        """Validate the knowledge base: validate"""
        errors = self.engine.validate_knowledge_base()
        if errors:
            print("Validation errors:")
            for error in errors:
                print(f"  {error}")
        else:
            print("Knowledge base is valid.")
    
    def do_quit(self, arg):
        """Exit the program: quit"""
        print("Goodbye!")
        return True
    
    def do_exit(self, arg):
        """Exit the program: exit"""
        return self.do_quit(arg)
    
    def default(self, line):
        """Handle commands that don't match any do_* method."""
        if line.startswith('?-'):
            # This is a query
            self.do_query(line[2:].strip())
        elif line.endswith('.'):
            # This is a fact or rule
            try:
                self.engine.parse(line, "input")
                self.engine.optimize()
                print("Added fact/rule.")
            except Exception as e:
                print(f"Error adding fact/rule: {e}")
        else:
            print(f"Unknown command: {line}")
            print("Type 'help' for available commands.")

def cli_mode():
    """Run the CLI version of the app."""
    parser = argparse.ArgumentParser(description="Advanced Logic Programming System")
    parser.add_argument("--file", "-f", help="Load a logic file on startup")
    parser.add_argument("--query", "-q", help="Execute a query and exit")
    parser.add_argument("--debug", action="store_true", help="Enable debugging on startup")
    parser.add_argument("--parallel", action="store_true", help="Enable parallel execution on startup")
    parser.add_argument("--trace", action="store_true", help="Enable tracing on startup")
    
    args, remaining = parser.parse_known_args()
    
    # Create engine
    engine = LogicEngine()
    
    # Apply startup options
    if args.debug:
        engine.debugger_active = True
    if args.parallel:
        engine.parallel_enabled = True
    if args.trace:
        engine.trace_enabled = True
    
    # Load file if specified
    if args.file:
        try:
            with open(args.file, 'r') as f:
                content = f.read()
            engine.parse(content, args.file)
            engine.optimize()
            print(f"Loaded {args.file} successfully.")
        except Exception as e:
            print(f"Error loading {args.file}: {e}")
            sys.exit(1)
    
    # Execute query if specified
    if args.query:
        try:
            solutions = []
            for solution in engine.query(args.query):
                solutions.append(solution)
            
            # Extract variable names from the query
            var_names = list(set(re.findall(r'\b[A-Z]\w*\b', args.query)))
            
            if solutions:
                if var_names:
                    for i, solution in enumerate(solutions):
                        print(f"Solution {i+1}:")
                        for var in var_names:
                            if var in solution:
                                print(f"  {var} = {format_term(substitute(var, solution))}")
                else:
                    print("Yes")
            else:
                print("No solutions found.")
        except Exception as e:
            print(f"Error executing query: {e}")
            sys.exit(1)
        sys.exit(0)
    
    # Start interactive shell
    shell = LogicShell(engine)
    shell.cmdloop()

if __name__ == "__main__":
    cli_mode()