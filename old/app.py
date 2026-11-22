import re
import pickle
import readline
import os
import json
import threading
import time
from collections import defaultdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Parsing helpers ---

def split_args(text):
    """Split arguments while handling nested parentheses"""
    args = []
    depth = 0
    start = 0
    for i, c in enumerate(text):
        if c == ',' and depth == 0:
            args.append(text[start:i].strip())
            start = i + 1
        elif c in '([':
            depth += 1
        elif c in ')]':
            depth -= 1
    args.append(text[start:].strip())
    return [a for a in args if a]

def parse_term(text):
    """Parse a term into internal representation"""
    text = text.strip()
    # Number parsing - improved to handle negative numbers and decimals
    if text.replace('.', '', 1).replace('-', '', 1).isdigit() and (text.count('.') <= 1):
        if '.' in text:
            return float(text)
        else:
            return int(text)
    # String parsing (quoted atoms)
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    # List parsing
    if text.startswith('[') and text.endswith(']'):
        return parse_list(text[1:-1].strip())
    # Compound term parsing
    match = re.match(r'^(\w+)\((.*)\)$', text)
    if match:
        name = match.group(1)
        args = split_args(match.group(2))
        return (name, tuple(parse_term(arg) for arg in args))
    # Variable or atom
    return text

def parse_list(text):
    """Parse list notation into cons/nil representation"""
    if not text or text == '':
        return ('nil',)
    if '|' in text:
        head_text, tail_text = map(str.strip, text.split('|', 1))
        head = parse_term(head_text)
        tail = parse_term(tail_text)
        return ('cons', head, tail)
    items = split_args(text)
    if not items:
        return ('nil',)
    result = ('nil',)
    for item in reversed(items):
        result = ('cons', parse_term(item), result)
    return result

def format_term(term):
    """Convert internal term representation to string"""
    if isinstance(term, (int, float)):
        return str(term)
    if isinstance(term, str) and (term.startswith('"') or term.startswith("'")):
        return term
    if isinstance(term, tuple):
        if term[0] == 'nil':
            return '[]'
        if term[0] == 'cons':
            head = format_term(term[1])
            tail = format_term(term[2])
            if tail == '[]':
                return f"[{head}]"
            elif isinstance(tail, str) and tail.startswith('['):
                return f"[{head}, {tail[1:-1]}]"
            else:
                return f"[{head}|{tail}]"
        name = term[0]
        args = ', '.join(format_term(a) for a in term[1:])
        return f"{name}({args})"
    else:
        return str(term)

def is_variable(x):
    """Check if a term is a variable (starts with uppercase)"""
    return isinstance(x, str) and x and x[0].isupper()

# --- Substitution helper ---

def substitute(term, env):
    """Apply environment substitutions to a term"""
    if isinstance(term, str):
        return env.get(term, term)
    if isinstance(term, tuple):
        if len(term) == 0:
            return term
        return (term[0],) + tuple(substitute(t, env) for t in term[1:])
    return term

# --- Unification ---

def deref(term, env):
    """Dereference a term through the environment"""
    while isinstance(term, str) and term in env:
        term = env[term]
    return term

def occurs_check(var, term, env):
    """Check if variable occurs in term (prevents infinite loops)"""
    term = deref(term, env)
    if var == term:
        return True
    if isinstance(term, tuple):
        return any(occurs_check(var, t, env) for t in term[1:])
    return False

def unify(x, y, env):
    """Unify two terms with the given environment"""
    env = env.copy()

    def deref(term):
        while isinstance(term, str) and term in env:
            term = env[term]
        return term

    x = deref(x)
    y = deref(y)

    if x == y:
        return env

    if is_variable(x):
        if occurs_check(x, y, env):
            return None
        env[x] = y
        return env

    if is_variable(y):
        if occurs_check(y, x, env):
            return None
        env[y] = x
        return env

    if isinstance(x, tuple) and isinstance(y, tuple):
        if len(x) == 0 or len(y) == 0:
            return None
        if x[0] != y[0] or len(x) != len(y):
            return None
        for a, b in zip(x[1:], y[1:]):
            env = unify(a, b, env)
            if env is None:
                return None
        return env

    return None

# --- Cut support ---

class CutException(Exception):
    """Exception to handle cut operations"""
    pass

class ResolveContext:
    """Context for tracking cut operations during resolution"""
    def __init__(self):
        self.cut = False

# --- Advanced Logic Engine ---

class LogicEngine:
    """Main logic programming engine with advanced features"""
    
    def __init__(self):
        # --- Core attributes ---
        self.facts = defaultdict(list)
        self.rules = []
        self.constraints = defaultdict(list)
        self.memo = {}
        self.trace_enabled = False
        self.stats_enabled = False
        self.query_count = 0
        self.resolve_count = 0
        self.loaded_files = set()
        self.indexed_facts = defaultdict(lambda: defaultdict(list))
        self.compiled_rules = {}
        self.profile_data = defaultdict(lambda: {'calls': 0, 'time': 0.0})
        self.call_stack = []
        self.type_constraints = {}

        # --- Feature 1: Tabling/Memoization ---
        self.tabled_predicates = set()
        self.memo_table = defaultdict(list) # Key: (pred, args_tuple), Value: list of solution envs

        # --- Feature 2: Foreign Function Interface ---
        self.foreign_functions = {} # Key: (pred, arity), Value: python_callable

        # --- Feature 3: Debugger ---
        self.debugger_active = False
        self.breakpoints = set()
        self.debugger_step_mode = False
        self.debugger_skip_depth = -1

        # --- Feature 5: Constraints (CLP(FD)) ---
        self.constraint_store = {} # Key: Var, Value: set of possible integers (domain)
        self.constraint_queue = [] # List of constraint functions to process

        # --- Feature 6: Parallel Execution ---
        self.parallel_enabled = False
        self.thread_pool = None

    # --- Configuration methods ---
    
    def enable_trace(self, enabled=True):
        """Enable/disable resolution tracing"""
        self.trace_enabled = enabled

    def enable_stats(self, enabled=True):
        """Enable/disable statistics collection"""
        self.stats_enabled = enabled

    # --- Parsing methods (with DCG support) ---
    
    def parse(self, program, filename="input"):
        """Parse a program string into facts and rules"""
        lines = program.strip().splitlines()
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('%'):
                continue
            if not line.endswith('.'):
                raise ValueError(f"Line {i} in {filename} must end with '.': {line}")
            line = line[:-1].strip()
            
            # Feature 4: DCG Rule Parsing
            if '-->' in line:
                self._parse_dcg_rule(line, filename, i)
            elif ':-' in line:
                self._parse_rule(line, filename, i)
            else:
                self._parse_fact(line, filename, i)

    def _parse_fact(self, line, filename="input", line_num=1):
        """Parse a single fact"""
        try:
            name, args = self._parse_predicate(line)
            self.facts[name].append(tuple(args))
        except Exception as e:
            raise ValueError(f"Error parsing fact at {filename}:{line_num}: {e}")

    def _parse_rule(self, line, filename="input", line_num=1):
        """Parse a single rule"""
        try:
            head, body = map(str.strip, line.split(':-'))
            head_name, head_args = self._parse_predicate(head)
            body_parts = [self._parse_predicate(part.strip()) for part in split_args(body)]
            self.rules.append((head_name, head_args, body_parts))
        except Exception as e:
            raise ValueError(f"Error parsing rule at {filename}:{line_num}: {e}")

    # Feature 4: DCG Rule Expansion
    def _parse_dcg_rule(self, line, filename="input", line_num=1):
        """Parse and expand a DCG rule into a standard Prolog rule"""
        try:
            head, body = map(str.strip, line.split('-->'))
            head_name, head_args = self._parse_predicate(head)
            
            # DCG heads have two implicit list arguments: Start and End
            if len(head_args) > 0:
                raise ValueError("DCG rule head cannot have arguments")
            
            s0, s = ('S0',), ('S',)
            head_pred = (head_name, s0, s)

            body_goals = self._expand_dcg_body(body)
            self.rules.append((head_pred[0], head_pred[1:], body_goals))
        except Exception as e:
            raise ValueError(f"Error parsing DCG rule at {filename}:{line_num}: {e}")

    def _expand_dcg_body(self, body_text):
        """Expand the body of a DCG rule into a list of standard goals"""
        goals = []
        s0, s1, s2 = ('S0',), ('S1',), ('S2',)
        
        # The current "input" and "output" list pointers
        current_in, current_out = s0, s1

        items = split_args(body_text)
        for item in items:
            item = item.strip()
            # Terminal: [the, cat]
            if item.startswith('[') and item.endswith(']'):
                terminal_list = parse_term(item)
                # Connects the list of terminals to the difference list pointers
                goals.append(('connects', terminal_list, current_in[0], current_out[0]))
            # Non-terminal: noun_phrase
            else:
                non_term = self._parse_predicate(item)
                goals.append((non_term[0],) + non_term[1] + (current_in[0], current_out[0]))
            
            # Shift pointers for the next item
            current_in, current_out = current_out, s2

        return goals

    def _parse_predicate(self, text):
        """Parse a predicate name and arguments"""
        text = text.strip()
        match = re.match(r'^(\w+)(?:\((.*?)\))?$', text)
        if not match:
            raise ValueError(f"Invalid predicate: {text}")
        name = match.group(1)
        args_text = match.group(2)
        if args_text is None:
            return name, []
        args = split_args(args_text)
        parsed_args = [parse_term(arg) for arg in args]
        return name, parsed_args

    # --- Knowledge base manipulation ---
    
    def add_constraint(self, predicate, constraint_func):
        """Add a constraint function for a predicate"""
        self.constraints[predicate].append(constraint_func)

    def add_type_constraint(self, predicate, arg_types):
        """Add type constraints for predicate arguments"""
        self.type_constraints[predicate] = arg_types
        def type_checker(args, env):
            for i, (arg, expected_type) in enumerate(zip(args, arg_types)):
                resolved_arg = substitute(arg, env)
                if expected_type == 'number' and not isinstance(resolved_arg, (int, float)):
                    return False
                if expected_type == 'list' and not (isinstance(resolved_arg, tuple) and 
                                                  resolved_arg[0] in ('nil', 'cons')):
                    return False
                if expected_type == 'atom' and not isinstance(resolved_arg, str):
                    return False
                if expected_type == 'variable' and not is_variable(resolved_arg):
                    return False
            return True
        self.add_constraint(predicate, type_checker)

    def assertz(self, fact_or_rule):
        """Add a fact or rule at the end"""
        if '-->' in fact_or_rule:
            self._parse_dcg_rule(fact_or_rule)
        elif ':-' in fact_or_rule:
            self._parse_rule(fact_or_rule)
        else:
            self._parse_fact(fact_or_rule)

    def asserta(self, fact_or_rule):
        """Add a fact or rule at the beginning"""
        if '-->' in fact_or_rule:
            self._parse_dcg_rule(fact_or_rule)
            self.rules.reverse() # Hacky, but works for now
        elif ':-' in fact_or_rule:
            head, body = map(str.strip, fact_or_rule.split(':-'))
            head_name, head_args = self._parse_predicate(head)
            body_parts = [self._parse_predicate(part.strip()) for part in split_args(body)]
            self.rules.insert(0, (head_name, head_args, body_parts))
        else:
            name, args = self._parse_predicate(fact_or_rule)
            self.facts[name].insert(0, tuple(args))

    def retract(self, pattern):
        """Remove facts or rules matching pattern"""
        name, args = self._parse_predicate(pattern)
        
        # Remove facts
        if name in self.facts:
            original_facts = self.facts[name][:]
            self.facts[name] = []
            for fact in original_facts:
                env = {}
                match = True
                for pattern_arg, fact_arg in zip(args, fact):
                    result = unify(pattern_arg, fact_arg, env)
                    if result is None:
                        match = False
                        break
                    env = result
                if not match:
                    self.facts[name].append(fact)
        
        # Remove rules
        original_rules = self.rules[:]
        self.rules = []
        for rule in original_rules:
            if rule[0] == name and len(rule[1]) == len(args):
                env = {}
                match = True
                for pattern_arg, rule_arg in zip(args, rule[1]):
                    result = unify(pattern_arg, rule_arg, env)
                    if result is None:
                        match = False
                        break
                    env = result
                if not match:
                    self.rules.append(rule)
            else:
                self.rules.append(rule)

    # --- Feature 1: Tabling/Memoization ---
    def table(self, predicate_signature):
        """Mark a predicate for tabling. E.g., table('ancestor/2')"""
        self.tabled_predicates.add(predicate_signature)

    # --- Feature 2: Foreign Function Interface ---
    def register_foreign(self, predicate_signature, python_function):
        """Register a Python function as a foreign predicate."""
        try:
            name, arity_str = predicate_signature.split('/')
            arity = int(arity_str)
            self.foreign_functions[(name, arity)] = python_function
            print(f"Registered foreign predicate: {predicate_signature}")
        except (ValueError, IndexError):
            print(f"Invalid predicate signature for foreign function: {predicate_signature}. Use format 'name/arity'.")

    # --- Feature 3: Debugger ---
    def debugger_set_breakpoint(self, predicate_signature):
        """Set a breakpoint on a predicate. E.g., break('parent/2')"""
        self.breakpoints.add(predicate_signature)
        print(f"Breakpoint set on {predicate_signature}")

    def debugger_clear_breakpoint(self, predicate_signature):
        """Clear a breakpoint on a predicate."""
        self.breakpoints.discard(predicate_signature)
        print(f"Breakpoint cleared on {predicate_signature}")

    def _debugger_prompt(self, name, args, env, depth):
        """Interactive debugger prompt."""
        self.call_stack.append((name, args, depth))
        while True:
            try:
                cmd = input(f"DEBUG ({name}/{len(args)}): d(ebug), s(tep), n(ext), c(ontinue), p(rint) <var>, h(elp)? ").strip().lower()
                if cmd == 'c' or cmd == 'continue':
                    self.debugger_active = False
                    break
                if cmd == 's' or cmd == 'step':
                    self.debugger_step_mode = True
                    break
                if cmd == 'n' or cmd == 'next':
                    self.debugger_step_mode = True
                    self.debugger_skip_depth = depth
                    break
                if cmd.startswith('p ') or cmd.startswith('print '):
                    var_name = cmd.split(' ', 1)[1].strip()
                    if var_name in env:
                        print(f"{var_name} = {format_term(substitute(var_name, env))}")
                    else:
                        print(f"{var_name} is not bound in this context.")
                elif cmd == 'h' or cmd == 'help':
                    print("  c(ontinue): Run until next breakpoint")
                    print("  s(tep): Step to next call")
                    print("  n(ext): Step over this call")
                    print("  p(rint) <var>: Print variable binding")
                    print("  h(elp): Show this help")
                else:
                    print("Unknown command.")
            except (EOFError, KeyboardInterrupt):
                print("\nExiting debugger.")
                self.debugger_active = False
                break
        self.call_stack.pop()


    # --- Query execution ---
    
    def query(self, q, max_solutions=None, timeout=None):
        """Execute a query with optional limits"""
        self.query_count += 1
        start_time = datetime.now()
        solutions_found = 0
        
        # Feature 5: Initialize constraint store for each query
        self.constraint_store.clear()
        self.constraint_queue.clear()
        
        name, args = self._parse_predicate(q)
        context = ResolveContext()
        
        # Feature 6: Parallel execution
        if self.parallel_enabled and not self.thread_pool:
            self.thread_pool = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)

        def check_timeout():
            if timeout and (datetime.now() - start_time).total_seconds() > timeout:
                return True
            return False
        
        try:
            for result in self._resolve(name, args, {}, context, 0):
                if check_timeout():
                    print("Query timeout reached")
                    break
                
                solutions_found += 1
                yield result
                
                if max_solutions and solutions_found >= max_solutions:
                    break
        finally:
            if self.thread_pool:
                self.thread_pool.shutdown(wait=True)
                self.thread_pool = None


    def _resolve(self, name, args, env, context, depth=0):
        """Internal resolution method with all features integrated"""
        if context.cut:
            return

        if self.stats_enabled:
            self.resolve_count += 1
            self.profile_data[f"{name}/{len(args)}"]['calls'] += 1

        start_time = time.time()
        self.call_stack.append((name, args, depth))
        
        # --- Feature 3: Debugger Check ---
        pred_sig = f"{name}/{len(args)}"
        if self.debugger_active and (pred_sig in self.breakpoints or self.debugger_step_mode):
            if self.debugger_skip_depth == -1 or depth <= self.debugger_skip_depth:
                self._debugger_prompt(name, args, env, depth)
                self.debugger_step_mode = False
                self.debugger_skip_depth = -1
        
        if self.trace_enabled:
            indent = "  " * depth
            args_str = ", ".join(format_term(a) for a in args)
            print(f"{indent}CALL: {name}({args_str})")

        try:
            # --- Feature 2: Foreign Function Interface Check ---
            ffi_key = (name, len(args))
            if ffi_key in self.foreign_functions:
                func = self.foreign_functions[ffi_key]
                resolved_args = [substitute(a, env) for a in args]
                try:
                    # The foreign function should be a generator yielding solution dicts
                    for solution_env in func(*resolved_args):
                        new_env = env.copy()
                        new_env.update(solution_env)
                        yield new_env
                except Exception as e:
                    print(f"Error in foreign function {pred_sig}: {e}")
                return

            # --- Feature 1: Tabling/Memoization Check ---
            if pred_sig in self.tabled_predicates:
                # Create a canonical key from dereferenced arguments
                key_args = tuple(deref(a, env) for a in args)
                memo_key = (name, key_args)
                
                if memo_key in self.memo_table:
                    # Yield all previously computed solutions
                    for solution_env in self.memo_table[memo_key]:
                        yield solution_env.copy()
                    return
                
                # If not computed, compute and store
                solutions = []
                for solution in self._resolve_original(name, args, env, context, depth):
                    solutions.append(solution.copy())
                    yield solution
                self.memo_table[memo_key] = solutions
                return

            # --- Original Resolution Logic (if not tabled) ---
            yield from self._resolve_original(name, args, env, context, depth)

        except Exception as e:
            if self.trace_enabled:
                indent = "  " * depth
                print(f"{indent}ERROR in {name}: {e}")
            raise
        finally:
            duration = time.time() - start_time
            if self.stats_enabled:
                self.profile_data[f"{name}/{len(args)}"]['time'] += duration
            self.call_stack.pop()

    def _resolve_original(self, name, args, env, context, depth):
        """The original resolution logic, now separated for tabling."""
        # Built-in predicates
        builtin_result = self._handle_builtins(name, args, env, context, depth)
        if builtin_result is not None:
            yield from builtin_result
            return

        # Check type constraints
        if name in self.type_constraints:
            if not self._check_type_constraints(name, args, env):
                return

        # Check custom constraints
        if name in self.constraints:
            constraint_passed = True
            for constraint_func in self.constraints[name]:
                try:
                    if not constraint_func(args, env):
                        constraint_passed = False
                        break
                except:
                    constraint_passed = False
                    break
            if not constraint_passed:
                return

        # Use indexed facts for faster lookup
        if name in self.indexed_facts and args:
            first_arg = substitute(args[0], env)
            if isinstance(first_arg, str) and not is_variable(first_arg):
                facts_to_try = self.indexed_facts[name].get(first_arg, [])
                for fact in facts_to_try:
                    if context.cut:
                        return
                    match = unify(args, fact, env)
                    if match is not None:
                        yield match
                return

        # --- Feature 6: Parallel Execution ---
        alternatives = []

        # Regular fact resolution
        for fact in self.facts.get(name, []):
            alternatives.append(('fact', fact))

        # Rule resolution
        rule_key = (name, len(args))
        rules_to_try = self.compiled_rules.get(rule_key, [])
        for rule in rules_to_try:
            alternatives.append(('rule', rule))

        if self.parallel_enabled and len(alternatives) > 1:
            futures = []
            for alt_type, alt_data in alternatives:
                future = self.thread_pool.submit(self._resolve_alternative, alt_type, alt_data, args, env, context, depth)
                futures.append(future)
            
            for future in as_completed(futures):
                if context.cut: break
                for result in future.result():
                    yield result
        else:
            for alt_type, alt_data in alternatives:
                if context.cut: return
                for result in self._resolve_alternative(alt_type, alt_data, args, env, context, depth):
                    yield result

    def _resolve_alternative(self, alt_type, alt_data, args, env, context, depth):
        """Resolves a single alternative (fact or rule)"""
        if alt_type == 'fact':
            fact = alt_data
            match = unify(args, fact, env)
            if match is not None:
                yield match
        elif alt_type == 'rule':
            rule_name, rule_head, rule_body = alt_data
            head_match = unify(rule_head, args, env)
            if head_match is not None:
                yield from self._resolve_body(rule_body, head_match, context, depth + 1)

    def _handle_builtins(self, name, args, env, context, depth):
        """Handle built-in predicates, including constraints and DCGs"""
        # --- Feature 5: CLP(FD) Constraints ---
        if name in ('ins', '#=', '#\\=', '#<', '#>', '#=<', '#>='):
            # This is a constraint, add it to the store and succeed for now
            # The actual solving happens with `labeling/1`
            self.constraint_queue.append((name, args, env.copy()))
            yield env.copy()
            return []

        # --- Feature 4: DCG Helper ---
        if name == 'connects' and len(args) == 3:
            list_term, in_list, out_list = args
            # This is a complex unification. `connects([a,b], L0, L2)` should unify
            # L0 with `[a,b|L2]`. We need a helper for this.
            # Let's simplify: `connects([a,b], S0, S)` means `S0 = [a,b|S]`
            if isinstance(list_term, tuple) and list_term[0] == 'cons':
                # This is not right. `connects` should unify `S0` with `list_term + S`.
                # Let's use append: append(list_term, S, S0)
                append_goal = ('append', list_term, out_list, in_list)
                yield from self._resolve('append', append_goal[1:], env, context, depth)
            elif list_term == ('nil',):
                # `connects([], S0, S)` means `S0 = S`
                new_env = unify(in_list, out_list, env.copy())
                if new_env: yield new_env
            return []

        # ... (rest of the built-ins from the previous version) ...
        # Basic built-ins
        if name == 'true' and len(args) == 0: yield env; return []
        if name == 'fail' and len(args) == 0: return []
        if name == 'eq' and len(args) == 2:
            if unify(args[0], args[1], env) is not None: yield env
            return []
        if name == 'write' and len(args) == 1:
            print(format_term(substitute(args[0], env)), end=''); yield env; return []
        if name == 'nl' and len(args) == 0: print(); yield env; return []
        if name == 'not' and len(args) == 1:
            neg_goal = args[0]; neg_context = ResolveContext()
            found_solution = False
            for _ in self._resolve(neg_goal[0], neg_goal[1:], env.copy(), neg_context, depth + 1):
                found_solution = True; break
            if not found_solution: yield env
            return []
        if name == 'cut' and len(args) == 0: context.cut = True; yield env; return []
        
        # Arithmetic built-ins
        if name == 'is' and len(args) == 2:
            left = substitute(args[0], env); right = substitute(args[1], env)
            if isinstance(right, (int, float)):
                new_env = unify(left, right, env.copy())
                if new_env is not None: yield new_env
            return []
        if name == 'lt' and len(args) == 2:
            left = substitute(args[0], env); right = substitute(args[1], env)
            if isinstance(left, (int, float)) and isinstance(right, (int, float)) and left < right: yield env
            return []
        if name == 'gt' and len(args) == 2:
            left = substitute(args[0], env); right = substitute(args[1], env)
            if isinstance(left, (int, float)) and isinstance(right, (int, float)) and left > right: yield env
            return []
        
        # List built-ins
        if name == 'append' and len(args) == 3:
            list1 = substitute(args[0], env); list2 = substitute(args[1], env); result = substitute(args[2], env)
            def append_lists(l1, l2):
                if l1 == ('nil',): return l2
                if isinstance(l1, tuple) and l1[0] == 'cons': return ('cons', l1[1], append_lists(l1[2], l2))
                return None
            appended = append_lists(list1, list2)
            if appended is not None:
                new_env = unify(result, appended, env.copy())
                if new_env is not None: yield new_env
            return []
        
        # --- Feature 5: CLP(FD) Labeling ---
        if name == 'labeling' and len(args) == 1:
            vars_to_label = substitute(args[0], env)
            if not (isinstance(vars_to_label, tuple) and vars_to_label[0] == 'cons'):
                return # Not a list of variables
            
            # Get all variables in the list
            vars = []
            current = vars_to_label
            while current[0] == 'cons':
                var = current[1]
                if is_variable(var): vars.append(var)
                current = current[2]
            
            if not vars: yield env; return

            # Find the first variable with a domain
            var_to_label = None
            for v in vars:
                if v in self.constraint_store:
                    var_to_label = v; break
            
            if not var_to_label:
                # No more constrained vars, just assign 0 to remaining unbound vars
                new_env = env.copy()
                for v in vars:
                    if v not in new_env: new_env[v] = 0
                yield new_env
                return

            # Try each value in the domain
            domain = self.constraint_store[var_to_label]
            for val in sorted(list(domain)):
                new_env = env.copy()
                new_env[var_to_label] = val
                
                # Propagate constraints with this new assignment
                if self._propagate_constraints(new_env):
                    # Recurse to label the rest
                    yield from self._handle_builtins('labeling', [vars_to_label], new_env, context, depth)
            return []


        # Not a built-in
        return None

    def _propagate_constraints(self, env):
        """Propagate all queued constraints given the current environment."""
        # This is a very naive constraint solver. Real ones are much more complex.
        temp_queue = list(self.constraint_queue)
        self.constraint_queue.clear()
        
        for name, args, c_env in temp_queue:
            # Merge the environment from when the constraint was created with the current one
            current_env = {**c_env, **env}
            resolved_args = [substitute(a, current_env) for a in args]

            if name == 'ins':
                # `Vars in 1..10`
                vars, domain_term = resolved_args
                domain = set()
                if isinstance(domain_term, tuple) and domain_term[0] == '..':
                    start, end = substitute(domain_term[1], current_env), substitute(domain_term[2], current_env)
                    if isinstance(start, int) and isinstance(end, int):
                        domain = set(range(start, end + 1))
                
                if isinstance(vars, tuple) and vars[0] == 'cons':
                    current = vars
                    while current[0] == 'cons':
                        var = current[1]
                        if is_variable(var):
                            self.constraint_store[var] = domain
                        current = current[2]
            
            elif name == '#=':
                # `X #= Y + 1`
                left, right = resolved_args
                # This is very simplified. A real solver would handle expressions.
                if isinstance(left, str) and isinstance(right, (int, float)):
                    if left in self.constraint_store:
                        self.constraint_store[left] = {right}
                elif isinstance(right, str) and isinstance(left, (int, float)):
                    if right in self.constraint_store:
                        self.constraint_store[right] = {left}
                # ... more complex cases omitted for brevity ...
            
            elif name == '#<':
                left, right = resolved_args
                if isinstance(left, str) and isinstance(right, (int, float)):
                    if left in self.constraint_store:
                        self.constraint_store[left] = {v for v in self.constraint_store[left] if v < right}
                elif isinstance(right, str) and isinstance(left, (int, float)):
                    if right in self.constraint_store:
                        self.constraint_store[right] = {v for v in self.constraint_store[right] if v > left}

        # Prune domains of all variables to their intersection
        for var, domain in self.constraint_store.items():
            if not domain:
                return False # Inconsistent constraint
            # If a variable is now ground, remove it from the store
            if len(domain) == 1:
                env[var] = list(domain)[0]
                #del self.constraint_store[var]

        return True


    def _check_type_constraints(self, name, args, env):
        """Check type constraints for predicate arguments"""
        if name not in self.type_constraints: return True
        arg_types = self.type_constraints[name]
        for i, (arg, expected_type) in enumerate(zip(args, arg_types)):
            if i >= len(arg_types): break
            resolved_arg = substitute(arg, env)
            if expected_type == 'number' and not isinstance(resolved_arg, (int, float)): return False
            if expected_type == 'list' and not (isinstance(resolved_arg, tuple) and resolved_arg[0] in ('nil', 'cons')): return False
            if expected_type == 'atom' and not isinstance(resolved_arg, str): return False
            if expected_type == 'variable' and not is_variable(resolved_arg): return False
        return True

    def _resolve_body(self, body, env, context, depth):
        """Resolve the body of a rule"""
        if not body or context.cut: yield env; return
        name, args = body[0]; rest = body[1:]
        if name == 'cut' and len(args) == 0: context.cut = True; yield env; return
        for match in self._resolve(name, args, env.copy(), context, depth):
            yield from self._resolve_body(rest, match, context, depth)

    # --- Optimization and analysis ---
    
    def optimize(self):
        """Optimize the knowledge base for better performance"""
        self.indexed_facts = defaultdict(lambda: defaultdict(list))
        for pred, facts in self.facts.items():
            for fact in facts:
                if fact:
                    first_arg = fact[0]
                    if isinstance(first_arg, str) and not is_variable(first_arg):
                        self.indexed_facts[pred][first_arg].append(fact)
        self.compiled_rules = {}
        for rule in self.rules:
            key = (rule[0], len(rule[1]))
            if key not in self.compiled_rules: self.compiled_rules[key] = []
            self.compiled_rules[key].append(rule)

    def stats(self):
        """Return statistics about the knowledge base"""
        total_facts = sum(len(facts) for facts in self.facts.values())
        total_rules = len(self.rules)
        predicates = list(self.facts.keys()) + [rule[0] for rule in self.rules]
        return {
            'total_facts': total_facts, 'total_rules': total_rules,
            'unique_predicates': len(set(predicates)),
            'predicate_counts': {pred: len(self.facts.get(pred, [])) for pred in set(predicates)},
            'queries_executed': self.query_count, 'resolutions_performed': self.resolve_count,
            'files_loaded': list(self.loaded_files), 'type_constraints': dict(self.type_constraints)
        }

    def get_profile(self):
        """Return profiling information"""
        return dict(self.profile_data)

    def get_call_stack(self):
        """Return current call stack for debugging"""
        return self.call_stack.copy()

    def explain(self, goal):
        """Explain how a goal would be resolved"""
        name, args = self._parse_predicate(goal)
        print(f"Explanation for {goal}:")
        print(f"Facts: {len(self.facts.get(name, []))}")
        print(f"Rules: {len([r for r in self.rules if r[0] == name])}")
        for i, fact in enumerate(self.facts.get(name, [])): print(f"  Fact {i+1}: {name}{fact}")
        for i, (r_name, r_head, r_body) in enumerate(self.rules):
            if r_name == name:
                head_str = f"{r_name}{r_head}"; body_str = ', '.join(f"{n}{a}" for n, a in r_body)
                print(f"  Rule {i+1}: {head_str} :- {body_str}")

    def validate_knowledge_base(self):
        """Validate the entire knowledge base for consistency"""
        errors = []
        all_used = set()
        for rule in self.rules:
            for body_pred in rule[2]: all_used.add(body_pred[0])
        defined = set(self.facts.keys()) | {r[0] for r in self.rules}
        builtins = {'true', 'fail', 'eq', 'write', 'nl', 'not', 'cut', 'is', 'lt', 'gt', 
                   'append', 'connects', 'ins', '#=', '#\\=', '#<', '#>', '#=<', '#>=', 'labeling'}
        undefined = all_used - defined - builtins
        if undefined: errors.append(f"Undefined predicates: {undefined}")
        return errors

    # --- File I/O and serialization ---
    
    def save_state(self, filename):
        """Save entire engine state to file"""
        state = {
            'facts': dict(self.facts), 'rules': self.rules, 'constraints': dict(self.constraints),
            'type_constraints': self.type_constraints, 'stats': {'query_count': self.query_count, 'resolve_count': self.resolve_count},
            'loaded_files': list(self.loaded_files), 'profile_data': dict(self.profile_data)
        }
        with open(filename, 'wb') as f: pickle.dump(state, f)
        print(f"Engine state saved to {filename}")

    def load_state(self, filename):
        """Load engine state from file"""
        if not os.path.exists(filename): print(f"File not found: {filename}"); return False
        try:
            with open(filename, 'rb') as f: state = pickle.load(f)
            self.facts = defaultdict(list, state['facts']); self.rules = state['rules']
            self.constraints = defaultdict(list, state.get('constraints', {}))
            self.type_constraints = state.get('type_constraints', {})
            self.query_count = state['stats']['query_count']; self.resolve_count = state['stats']['resolve_count']
            self.loaded_files = set(state.get('loaded_files', []))
            self.profile_data = defaultdict(lambda: {'calls': 0, 'time': 0.0}, state.get('profile_data', {}))
            self.optimize(); print(f"Engine state loaded from {filename}"); return True
        except Exception as e: print(f"Error loading state: {e}"); return False

    def clear(self):
        """Clear the entire knowledge base"""
        self.facts.clear(); self.rules.clear(); self.constraints.clear(); self.type_constraints.clear()
        self.memo.clear(); self.loaded_files.clear(); self.indexed_facts.clear(); self.compiled_rules.clear()
        self.query_count = 0; self.resolve_count = 0; self.profile_data.clear(); self.call_stack.clear()
        self.tabled_predicates.clear(); self.memo_table.clear(); self.foreign_functions.clear()
        self.constraint_store.clear(); self.constraint_queue.clear()
        print("Knowledge base cleared")


# --- File I/O functions ---

def load_file(engine, filepath):
    """Load facts and rules from a file"""
    filepath = os.path.expanduser(filepath); filepath = os.path.abspath(filepath)
    if not os.path.exists(filepath): print(f"File not found: {filepath}"); return False
    try:
        with open(filepath, 'r') as f: content = f.read()
        if filepath.endswith('.state') or filepath.endswith('.pkl'): return engine.load_state(filepath)
        engine.parse(content, filepath); engine.loaded_files.add(filepath); engine.optimize()
        print(f"Loaded {filepath} successfully"); return True
    except Exception as e: print(f"Error loading {filepath}: {e}"); return False

def save_file(engine, filepath, format='prolog'):
    """Save current program to file"""
    try:
        if format == 'state' or filepath.endswith('.state') or filepath.endswith('.pkl'): engine.save_state(filepath); return True
        with open(filepath, 'w') as f:
            if engine.loaded_files: f.write("% Loaded files:\n"); [f.write(f"% - {loaded_file}\n") for loaded_file in engine.loaded_files]; f.write("\n")
            for pred, facts in sorted(engine.facts.items()):
                for fact in facts: args_str = ', '.join(format_term(a) for a in fact); f.write(f"{pred}({args_str}).\n")
                if facts: f.write("\n")
            for head_name, head_args, body_parts in engine.rules:
                head_str = f"{head_name}({', '.join(format_term(a) for a in head_args)})"
                body_str = ', '.join(f"{n}({', '.join(format_term(a) for a in args)})" for n, args in body_parts)
                f.write(f"{head_str} :- {body_str}.\n\n")
        print(f"Saved program to {filepath}"); return True
    except Exception as e: print(f"Error saving to {filepath}: {e}"); return False

def export_knowledge(engine, filepath, format='prolog'):
    """Export knowledge base in different formats"""
    try:
        if format == 'prolog': return save_file(engine, filepath)
        elif format == 'json':
            def term_to_dict(term):
                if isinstance(term, (int, float, str)): return term
                if isinstance(term, tuple):
                    if term[0] == 'nil': return {'type': 'list', 'value': []}
                    if term[0] == 'cons':
                        result = []; current = term
                        while current[0] == 'cons': result.append(term_to_dict(current[1])); current = current[2]
                        return {'type': 'list', 'value': result}
                    return {'type': 'compound', 'functor': term[0], 'args': [term_to_dict(arg) for arg in term[1:]]}
                return str(term)
            knowledge = {'facts': {pred: [term_to_dict(fact) for fact in facts] for pred, facts in engine.facts.items()},
                        'rules': [{'head': {'name': rule[0], 'args': [term_to_dict(arg) for arg in rule[1]]},
                                   'body': [{'name': part[0], 'args': [term_to_dict(arg) for arg in part[1]]} for part in rule[2]]}
                                  for rule in engine.rules],
                        'constraints': list(engine.constraints.keys()), 'type_constraints': engine.type_constraints, 'loaded_files': list(engine.loaded_files)}
            with open(filepath, 'w') as f: json.dump(knowledge, f, indent=2)
            print(f"Exported JSON to {filepath}"); return True
        else: print(f"Unknown format: {format}"); return False
    except Exception as e: print(f"Export error: {e}"); return False

# --- Foreign Function Example ---

def python_sum(a, b, result):
    """Example foreign function to sum two numbers."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        yield {result: a + b}

# --- REPL Interface ---

def repl():
    """Read-Eval-Print Loop for interactive usage"""
    print("🐍 Advanced MiniLogic REPL - Complete Logic Programming System")
    print("=" * 70)
    print("Features: Tabling, FFI, Debugger, DCGs, Constraints, Parallelism")
    print("Commands: load, save, table, foreign, break, debug, parallel, etc.")
    print("Facts/rules end with '.', DCGs with '-->', queries start with '?-'")
    print("=" * 70)
    
    engine = LogicEngine()
    engine.register_foreign('python_sum/3', python_sum)

    # Preload with comprehensive examples
    preload = """
    % Family relationships
    parent(john, mary). parent(mary, susan). parent(john, mark). parent(mark, alice).
    male(john). male(mark). female(mary). female(susan). female(alice).
    
    % Recursive rules (good for tabling)
    ancestor(X, Y) :- parent(X, Y).
    ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).

    % Feature 4: DCG Example
    sentence --> noun_phrase, verb_phrase.
    noun_phrase --> determiner, noun.
    verb_phrase --> verb.
    determiner --> [the].
    noun --> [cat]. noun --> [dog].
    verb --> [sleeps]. verb --> [runs].

    % Feature 5: Constraint Example
    magic_square([[A,B,C],[D,E,F],[G,H,I]]) :-
        [A,B,C,D,E,F,G,H,I] ins 1..9,
        all_different([A,B,C,D,E,F,G,H,I]),
        A+B+C #= 15, D+E+F #= 15, G+H+I #= 15,
        A+D+G #= 15, B+E+H #= 15, C+F+I #= 15,
        A+E+I #= 15, C+E+G #= 15.
    """
    
    engine.parse(preload, "preload")
    engine.optimize()
    print("Preloaded examples for tabling, DCGs, and constraints.\n")

    while True:
        try:
            line = input("MiniLogic> ").strip()
        except EOFError: print("\nGoodbye!"); break
        except KeyboardInterrupt: print("\nUse 'exit' to quit"); continue

        line = line.split('%', 1)[0].strip()
        if not line: continue

        if line.lower() == 'help':
            print("\n--- Commands ---")
            print("  load <file>          - Load a logic file")
            print("  save <file>          - Save current program")
            print("  clear                - Clear knowledge base")
            print("  stats                - Show statistics")
            print("  exit                 - Exit the REPL")
            print("\n--- Features ---")
            print("  table <pred/arity>   - Enable tabling for a predicate")
            print("  foreign <pred/arity> <func> - Register Python function")
            print("  break <pred/arity>   - Set a debugger breakpoint")
            print("  nobreak <pred/arity> - Clear a breakpoint")
            print("  debug on/off         - Enable/disable the debugger")
            print("  parallel on/off      - Enable/disable parallel execution")
            print("\n--- Querying ---")
            print("  ?- <goal>.           - Run a query")
            continue

        if line.lower() == 'exit': print("Goodbye!"); break

        # Feature Commands
        if line.lower().startswith('table '):
            engine.table(line[6:].strip()); continue
        if line.lower().startswith('foreign '):
            parts = line.split(maxsplit=2)
            if len(parts) == 3:
                # This is a simplified example, real FFI would need import logic
                print(f"FFI registration is manual in this example. See 'python_sum/3'.")
            continue
        if line.lower().startswith('break '):
            engine.debugger_set_breakpoint(line[6:].strip()); continue
        if line.lower().startswith('nobreak '):
            engine.debugger_clear_breakpoint(line[8:].strip()); continue
        if line.lower() == 'debug on':
            engine.debugger_active = True; print("Debugger enabled. Use 'break' to set breakpoints."); continue
        if line.lower() == 'debug off':
            engine.debugger_active = False; print("Debugger disabled."); continue
        if line.lower() == 'parallel on':
            engine.parallel_enabled = True; print("Parallel execution enabled."); continue
        if line.lower() == 'parallel off':
            engine.parallel_enabled = False; print("Parallel execution disabled."); continue

        # File I/O commands
        if line.lower().startswith('load '): load_file(engine, line[5:].strip()); continue
        if line.lower().startswith('save '):
            parts = line[5:].split(maxsplit=1); filename = parts[0]
            format = 'prolog'; save_file(engine, filename, format); continue
        if line.lower() == 'clear': engine.clear(); continue
        if line.lower() == 'stats':
            stats = engine.stats(); print(f"📊 Stats: {stats['total_facts']} facts, {stats['total_rules']} rules, {stats['queries_executed']} queries."); continue

        # Fact/Rule/DCG input
        if line.endswith('.'):
            try: engine.parse(line, "input"); engine.optimize(); print("✅ Added.")
            except Exception as e: print(f"❌ Parse error: {e}")
            continue

        # Query execution
        if line.startswith('?-'):
            query_text = line[2:].strip()
            if query_text.endswith('.'): query_text = query_text[:-1].strip()
            try:
                var_names = list(set(re.findall(r'\b[A-Z]\w*\b', query_text)))
                count = 0; start_time = datetime.now()
                for res in engine.query(query_text):
                    count += 1
                    if not var_names: print(f"✅ Solution {count}: True")
                    else:
                        solution = {var: format_term(substitute(var, res)) for var in var_names if var in res}
                        print(f"✅ Solution {count}: {solution}")
                duration = (datetime.now() - start_time).total_seconds()
                if count == 0: print("❌ No solutions found.")
                else: print(f"🔍 Found {count} solution(s) in {duration:.3f}s")
            except Exception as e: print(f"❌ Query error: {e}")
            continue

        print("❓ Invalid input. Type 'help' for commands.")

if __name__ == "__main__":
    repl()