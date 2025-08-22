import re
import pickle
import readline
import os
import json
from collections import defaultdict
from datetime import datetime

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
    # Number parsing
    if text.replace('.', '').replace('-', '').isdigit():
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
    if not text:
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
        return (term[0], tuple(substitute(t, env) for t in term[1:]))
    return term

# --- Unification ---

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
        if x[0] != y[0] or len(x) != len(y):
            return None
        for a, b in zip(x[1:], y[1:]):
            env = unify(a, b, env)
            if env is None:
                return None
        return env

    return None

def occurs_check(var, term, env):
    """Check if variable occurs in term (prevents infinite loops)"""
    term = deref(term, env)
    if var == term:
        return True
    if isinstance(term, tuple):
        return any(occurs_check(var, t, env) for t in term[1:])
    return False

def deref(term, env):
    """Dereference a term through the environment"""
    while isinstance(term, str) and term in env:
        term = env[term]
    return term

# --- Cut support ---

class CutException(Exception):
    """Exception to handle cut operations"""
    pass

class ResolveContext:
    """Context for tracking cut operations during resolution"""
    def __init__(self):
        self.cut = False

# --- Logic Engine ---

class LogicEngine:
    """Main logic programming engine with all features"""
    
    def __init__(self):
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

    # --- Configuration methods ---
    
    def enable_trace(self, enabled=True):
        """Enable/disable resolution tracing"""
        self.trace_enabled = enabled

    def enable_stats(self, enabled=True):
        """Enable/disable statistics collection"""
        self.stats_enabled = enabled

    # --- Parsing methods ---
    
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
            if ':-' in line:
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
        if ':-' in fact_or_rule:
            self._parse_rule(fact_or_rule)
        else:
            self._parse_fact(fact_or_rule)

    def asserta(self, fact_or_rule):
        """Add a fact or rule at the beginning"""
        if ':-' in fact_or_rule:
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
        
        if name in self.facts:
            self.facts[name] = [fact for fact in self.facts[name] 
                               if not all(unify(pattern_arg, fact_arg, {}) 
                                        for pattern_arg, fact_arg in zip(args, fact))]
        
        self.rules = [rule for rule in self.rules 
                     if not (rule[0] == name and 
                            all(unify(pattern_arg, rule_arg, {})
                               for pattern_arg, rule_arg in zip(args, rule[1])))]

    def clause(self, head, body):
        """Dynamic clause creation and addition"""
        if body == ('true',):
            self.assertz(format_term(head))
        else:
            head_str = format_term(head)
            body_str = format_term(body)
            self.assertz(f"{head_str} :- {body_str}.")

    def current_predicate(self, pattern):
        """Find all predicates matching pattern"""
        results = []
        for pred in self.facts.keys():
            if unify(pattern, pred, {}):
                results.append(pred)
        for rule in self.rules:
            if unify(pattern, rule[0], {}):
                results.append(rule[0])
        return list(set(results))

    def get_predicate_definition(self, predicate_name, arity):
        """Get all definitions for a predicate with given arity"""
        definitions = []
        
        # Get facts
        if predicate_name in self.facts:
            for fact in self.facts[predicate_name]:
                if len(fact) == arity:
                    definitions.append(('fact', fact))
        
        # Get rules
        for rule_name, rule_head, rule_body in self.rules:
            if rule_name == predicate_name and len(rule_head) == arity:
                definitions.append(('rule', (rule_head, rule_body)))
        
        return definitions

    # --- Query execution ---
    
    def query(self, q, max_solutions=None, timeout=None):
        """Execute a query with optional limits"""
        self.query_count += 1
        start_time = datetime.now()
        solutions_found = 0
        
        name, args = self._parse_predicate(q)
        context = ResolveContext()
        
        for result in self._resolve(name, args, {}, context, 0):
            if timeout and (datetime.now() - start_time).total_seconds() > timeout:
                print("Query timeout reached")
                break
            
            solutions_found += 1
            yield result
            
            if max_solutions and solutions_found >= max_solutions:
                break

    def _resolve(self, name, args, env, context, depth=0):
        """Internal resolution method with all built-ins"""
        if context.cut:
            return

        if self.stats_enabled:
            self.resolve_count += 1

        start_time = datetime.now()
        self.call_stack.append((name, args, depth))
        
        if self.trace_enabled:
            indent = "  " * depth
            args_str = ", ".join(format_term(a) for a in args)
            print(f"{indent}TRY: {name}({args_str})")

        try:
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
                            if self.trace_enabled:
                                args_str = ", ".join(format_term(a) for a in args)
                                print(f"{indent}SUCCESS INDEXED: {name}({args_str})")
                            yield match
                    return

            # Regular fact resolution
            for fact in self.facts.get(name, []):
                if context.cut:
                    return
                match = unify(args, fact, env)
                if match is not None:
                    if self.trace_enabled:
                        args_str = ", ".join(format_term(a) for a in args)
                        print(f"{indent}SUCCESS FACT: {name}({args_str})")
                    yield match

            # Rule resolution
            rule_key = (name, len(args))
            rules_to_try = self.compiled_rules.get(rule_key, [])
            for rule_name, rule_head, rule_body in rules_to_try:
                if context.cut:
                    return
                head_match = unify(rule_head, args, env)
                if head_match is None:
                    continue
                yield from self._resolve_body(rule_body, head_match, context, depth + 1)

        except Exception as e:
            if self.trace_enabled:
                indent = "  " * depth
                print(f"{indent}ERROR in {name}: {e}")
            raise
        finally:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            if self.stats_enabled:
                self.profile_data[name]['time'] += duration
            self.call_stack.pop()

    def _handle_builtins(self, name, args, env, context, depth):
        """Handle built-in predicates"""
        # Basic built-ins
        if name == 'true' and len(args) == 0:
            yield env
            return []

        if name == 'fail' and len(args) == 0:
            return []

        if name == 'eq' and len(args) == 2:
            if unify(args[0], args[1], env) is not None:
                yield env
            return []

        if name == 'write' and len(args) == 1:
            val = substitute(args[0], env)
            print(format_term(val))
            yield env
            return []

        if name == 'not' and len(args) == 1:
            neg_pred = args[0]
            for _ in self._resolve(neg_pred[0], neg_pred[1:], env.copy(), context, depth + 1):
                return []
            yield env
            return []

        if name == 'cut' and len(args) == 0:
            context.cut = True
            yield env
            return []

        # Arithmetic built-ins
        if name == 'is' and len(args) == 2:
            left = substitute(args[0], env)
            right = substitute(args[1], env)
            if isinstance(right, str) and right.replace('.', '').replace('-', '').isdigit():
                result = float(right) if '.' in right else int(right)
                new_env = unify(left, result, env.copy())
                if new_env is not None:
                    yield new_env
            return []

        if name == 'lt' and len(args) == 2:
            left = substitute(args[0], env)
            right = substitute(args[1], env)
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                if left < right:
                    yield env
            return []

        if name == 'gt' and len(args) == 2:
            left = substitute(args[0], env)
            right = substitute(args[1], env)
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                if left > right:
                    yield env
            return []

        # List built-ins
        if name == 'append' and len(args) == 3:
            list1 = substitute(args[0], env)
            list2 = substitute(args[1], env)
            result = substitute(args[2], env)
            
            def append_lists(l1, l2):
                if l1 == ('nil',):
                    return l2
                if isinstance(l1, tuple) and l1[0] == 'cons':
                    return ('cons', l1[1], append_lists(l1[2], l2))
                return None
            
            appended = append_lists(list1, list2)
            if appended is not None:
                new_env = unify(result, appended, env.copy())
                if new_env is not None:
                    yield new_env
            return []

        if name == 'length' and len(args) == 2:
            lst = substitute(args[0], env)
            length_var = args[1]
            
            def list_length(l, count=0):
                if l == ('nil',):
                    return count
                if isinstance(l, tuple) and l[0] == 'cons':
                    return list_length(l[2], count + 1)
                return None
            
            length = list_length(lst)
            if length is not None:
                new_env = unify(length_var, length, env.copy())
                if new_env is not None:
                    yield new_env
            return []

        # Advanced built-ins
        if name == 'arithmetic' and len(args) == 3:
            left = substitute(args[0], env)
            op = substitute(args[1], env)
            right = substitute(args[2], env)
            
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                result = None
                if op == '+': result = left + right
                elif op == '-': result = left - right
                elif op == '*': result = left * right
                elif op == '/': result = left / right if right != 0 else None
                elif op == 'mod': result = left % right if right != 0 else None
                elif op == '^': result = left ** right
                
                if result is not None:
                    yield env
            return []

        if name == 'compare' and len(args) == 3:
            left = substitute(args[0], env)
            op = substitute(args[1], env)
            right = substitute(args[2], env)
            
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                result = False
                if op == '==': result = left == right
                elif op == '!=': result = left != right
                elif op == '<': result = left < right
                elif op == '<=': result = left <= right
                elif op == '>': result = left > right
                elif op == '>=': result = left >= right
                
                if result:
                    yield env
            return []

        # Set operations
        if name == 'setof' and len(args) == 3:
            template = args[0]
            goal = args[1]
            result_var = args[2]
            
            solutions = set()
            for result_env in self._resolve(goal[0], goal[1:], env.copy(), context, depth + 1):
                solved_template = substitute(template, result_env)
                solutions.add(format_term(solved_template))
            
            # Convert back to list terms
            result_list = ('nil',)
            for solution_str in sorted(solutions):
                solution_term = parse_term(solution_str)
                result_list = ('cons', solution_term, result_list)
            
            new_env = unify(result_var, result_list, env.copy())
            if new_env is not None:
                yield new_env
            return []

        if name == 'bagof' and len(args) == 3:
            template = args[0]
            goal = args[1]
            result_var = args[2]
            
            solutions = []
            for result_env in self._resolve(goal[0], goal[1:], env.copy(), context, depth + 1):
                solved_template = substitute(template, result_env)
                solutions.append(solved_template)
            
            # Convert to list maintaining order
            result_list = ('nil',)
            for solution in reversed(solutions):
                result_list = ('cons', solution, result_list)
            
            new_env = unify(result_var, result_list, env.copy())
            if new_env is not None:
                yield new_env
            return []

        # Meta-programming
        if name == 'findall' and len(args) == 3:
            template = args[0]
            goal = args[1]
            output_var = args[2]
            
            if isinstance(goal, tuple) and len(goal) >= 1:
                solutions = []
                for result_env in self._resolve(goal[0], goal[1:], env.copy(), context, depth + 1):
                    solved_template = substitute(template, result_env)
                    solutions.append(solved_template)
                
                # Convert solutions to a list
                result_list = ('nil',)
                for solution in reversed(solutions):
                    result_list = ('cons', solution, result_list)
                
                new_env = unify(output_var, result_list, env.copy())
                if new_env is not None:
                    yield new_env
            return []

        # Not a built-in
        return None

    def _check_type_constraints(self, name, args, env):
        """Check type constraints for predicate arguments"""
        if name not in self.type_constraints:
            return True
        
        arg_types = self.type_constraints[name]
        for i, (arg, expected_type) in enumerate(zip(args, arg_types)):
            if i >= len(arg_types):
                break
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

    def _resolve_body(self, body, env, context, depth):
        """Resolve the body of a rule"""
        if not body or context.cut:
            yield env
            return
        
        name, args = body[0]
        rest = body[1:]

        if name == 'cut' and len(args) == 0:
            context.cut = True
            yield env
            return

        for match in self._resolve(name, args, env.copy(), context, depth):
            yield from self._resolve_body(rest, match, context, depth)

    # --- Optimization and analysis ---
    
    def optimize(self):
        """Optimize the knowledge base for better performance"""
        # Index facts by first argument for faster lookup
        self.indexed_facts = defaultdict(lambda: defaultdict(list))
        for pred, facts in self.facts.items():
            for fact in facts:
                if fact:  # Has at least one argument
                    first_arg = fact[0]
                    if isinstance(first_arg, str) and not is_variable(first_arg):
                        self.indexed_facts[pred][first_arg].append(fact)
        
        # Pre-compile frequently used rules
        self.compiled_rules = {}
        for rule in self.rules:
            key = (rule[0], len(rule[1]))
            if key not in self.compiled_rules:
                self.compiled_rules[key] = []
            self.compiled_rules[key].append(rule)

    def stats(self):
        """Return statistics about the knowledge base"""
        total_facts = sum(len(facts) for facts in self.facts.values())
        total_rules = len(self.rules)
        predicates = list(self.facts.keys()) + [rule[0] for rule in self.rules]
        
        return {
            'total_facts': total_facts,
            'total_rules': total_rules,
            'unique_predicates': len(set(predicates)),
            'predicate_counts': {pred: len(self.facts.get(pred, [])) for pred in set(predicates)},
            'queries_executed': self.query_count,
            'resolutions_performed': self.resolve_count,
            'files_loaded': list(self.loaded_files),
            'type_constraints': dict(self.type_constraints)
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
        
        for i, fact in enumerate(self.facts.get(name, [])):
            print(f"  Fact {i+1}: {name}{fact}")
        
        for i, (r_name, r_head, r_body) in enumerate(self.rules):
            if r_name == name:
                head_str = f"{r_name}{r_head}"
                body_str = ', '.join(f"{n}{a}" for n, a in r_body)
                print(f"  Rule {i+1}: {head_str} :- {body_str}")

    def validate_knowledge_base(self):
        """Validate the entire knowledge base for consistency"""
        errors = []
        
        # Check for undefined predicates
        all_used = set()
        for rule in self.rules:
            for body_pred in rule[2]:
                all_used.add(body_pred[0])
        
        defined = set(self.facts.keys()) | {r[0] for r in self.rules}
        builtins = {'true', 'fail', 'eq', 'write', 'not', 'cut', 'is', 'lt', 'gt', 
                   'append', 'length', 'arithmetic', 'compare', 'setof', 'bagof', 'findall'}
        undefined = all_used - defined - builtins
        
        if undefined:
            errors.append(f"Undefined predicates: {undefined}")
        
        # Check for arity mismatches
        predicate_arity = {}
        for pred, facts in self.facts.items():
            for fact in facts:
                if pred in predicate_arity:
                    if predicate_arity[pred] != len(fact):
                        errors.append(f"Arity mismatch for {pred}: {predicate_arity[pred]} vs {len(fact)}")
                else:
                    predicate_arity[pred] = len(fact)
        
        for rule in self.rules:
            pred, head, _ = rule
            if pred in predicate_arity:
                if predicate_arity[pred] != len(head):
                    errors.append(f"Arity mismatch for {pred}: {predicate_arity[pred]} vs {len(head)}")
            else:
                predicate_arity[pred] = len(head)
        
        return errors

    # --- File I/O and serialization ---
    
    def save_state(self, filename):
        """Save entire engine state to file"""
        state = {
            'facts': dict(self.facts),
            'rules': self.rules,
            'constraints': dict(self.constraints),
            'type_constraints': self.type_constraints,
            'stats': {
                'query_count': self.query_count,
                'resolve_count': self.resolve_count
            },
            'loaded_files': list(self.loaded_files),
            'profile_data': dict(self.profile_data)
        }
        with open(filename, 'wb') as f:
            pickle.dump(state, f)
        print(f"Engine state saved to {filename}")

    def load_state(self, filename):
        """Load engine state from file"""
        if not os.path.exists(filename):
            print(f"File not found: {filename}")
            return False
        
        try:
            with open(filename, 'rb') as f:
                state = pickle.load(f)
            self.facts = defaultdict(list, state['facts'])
            self.rules = state['rules']
            self.constraints = defaultdict(list, state.get('constraints', {}))
            self.type_constraints = state.get('type_constraints', {})
            self.query_count = state['stats']['query_count']
            self.resolve_count = state['stats']['resolve_count']
            self.loaded_files = set(state.get('loaded_files', []))
            self.profile_data = defaultdict(lambda: {'calls': 0, 'time': 0.0}, state.get('profile_data', {}))
            self.optimize()
            print(f"Engine state loaded from {filename}")
            return True
        except Exception as e:
            print(f"Error loading state: {e}")
            return False

    def clear(self):
        """Clear the entire knowledge base"""
        self.facts.clear()
        self.rules.clear()
        self.constraints.clear()
        self.type_constraints.clear()
        self.memo.clear()
        self.loaded_files.clear()
        self.indexed_facts.clear()
        self.compiled_rules.clear()
        self.query_count = 0
        self.resolve_count = 0
        self.profile_data.clear()
        self.call_stack.clear()
        print("Knowledge base cleared")

# --- File I/O functions ---

def load_file(engine, filepath):
    """Load facts and rules from a file"""
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return False
    
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Check if file is a state file
        if filepath.endswith('.state') or filepath.endswith('.pkl'):
            return engine.load_state(filepath)
        
        # Regular logic file
        engine.parse(content, filepath)
        engine.loaded_files.add(os.path.abspath(filepath))
        engine.optimize()
        print(f"Loaded {filepath} successfully")
        return True
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return False

def save_file(engine, filepath, format='prolog'):
    """Save current program to file"""
    try:
        if format == 'state' or filepath.endswith('.state') or filepath.endswith('.pkl'):
            engine.save_state(filepath)
            return True
        
        with open(filepath, 'w') as f:
            # Write loaded files as comments
            if engine.loaded_files:
                f.write("% Loaded files:\n")
                for loaded_file in engine.loaded_files:
                    f.write(f"% - {loaded_file}\n")
                f.write("\n")
            
            # Write facts
            for pred, facts in sorted(engine.facts.items()):
                for fact in facts:
                    args_str = ', '.join(format_term(a) for a in fact)
                    f.write(f"{pred}({args_str}).\n")
                if facts:
                    f.write("\n")
            
            # Write rules
            for head_name, head_args, body_parts in engine.rules:
                head_str = f"{head_name}({', '.join(format_term(a) for a in head_args)})"
                body_str = ', '.join(f"{n}({', '.join(format_term(a) for a in args)})" for n, args in body_parts)
                f.write(f"{head_str} :- {body_str}.\n\n")
        
        print(f"Saved program to {filepath}")
        return True
    except Exception as e:
        print(f"Error saving to {filepath}: {e}")
        return False

def export_knowledge(engine, filepath, format='prolog'):
    """Export knowledge base in different formats"""
    try:
        if format == 'prolog':
            return save_file(engine, filepath)
        elif format == 'json':
            knowledge = {
                'facts': {
                    pred: [list(fact) for fact in facts] 
                    for pred, facts in engine.facts.items()
                },
                'rules': [
                    {
                        'head': {'name': rule[0], 'args': list(rule[1])},
                        'body': [{'name': part[0], 'args': list(part[1])} for part in rule[2]]
                    }
                    for rule in engine.rules
                ],
                'constraints': list(engine.constraints.keys()),
                'type_constraints': engine.type_constraints,
                'loaded_files': list(engine.loaded_files)
            }
            with open(filepath, 'w') as f:
                json.dump(knowledge, f, indent=2)
            print(f"Exported JSON to {filepath}")
            return True
        else:
            print(f"Unknown format: {format}")
            return False
    except Exception as e:
        print(f"Export error: {e}")
        return False

# --- REPL Interface ---

def repl():
    """Read-Eval-Print Loop for interactive usage"""
    print("🐍 Advanced MiniLogic REPL - Complete Logic Programming System")
    print("=" * 70)
    print("Commands: load, save, save_state, load_state, export, clear, trace, stats")
    print("          explain, validate, profile, stack, type, optimize, exit")
    print("Facts/rules end with '.', queries start with '?-'")
    print("=" * 70)
    
    engine = LogicEngine()

    # Preload with comprehensive examples
    preload = """
    % Family relationships
    parent(john, mary).
    parent(mary, susan).
    parent(john, mark).
    parent(mark, alice).
    parent(susan, bob).
    
    % Gender facts
    male(john).
    male(mark).
    male(bob).
    female(mary).
    female(susan).
    female(alice).
    
    % Recursive rules
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
    
    reverse([], []).
    reverse([H|T], R) :- reverse(T, RT), append(RT, [H], R).
    
    % Arithmetic examples
    sum_list([], 0).
    sum_list([H|T], Sum) :- sum_list(T, Rest), Sum is H + Rest.
    
    % Age facts
    age(john, 50).
    age(mary, 30).
    age(mark, 28).
    age(susan, 5).
    age(alice, 3).
    age(bob, 1).
    
    % Conditional examples
    older_child(X, Y) :- parent(P, X), parent(P, Y), age(X, Ax), age(Y, Ay), Ax > Ay.
    can_drive(X) :- age(X, Age), Age >= 16.
    
    % Cut examples
    first_choice(X) :- option(X), cut.
    option(a).
    option(b).
    option(c).
    
    % Built-in examples
    print_hello :- write('Hello World!'), nl.
    test_equality :- eq(john, john), write('John equals John').
    
    % Type constraints (will be added programmatically)
    % :- add_type_constraint(parent, ['atom', 'atom'])
    % :- add_type_constraint(age, ['atom', 'number'])
    """

    # Add type constraints programmatically
    engine.add_type_constraint('parent', ['atom', 'atom'])
    engine.add_type_constraint('age', ['atom', 'number'])
    engine.add_type_constraint('male', ['atom'])
    engine.add_type_constraint('female', ['atom'])
    
    engine.parse(preload, "preload")
    engine.optimize()

    # Create example files if they don't exist
    if not os.path.exists('family.pl'):
        with open('family.pl', 'w') as f:
            f.write("""
% Sample family data
parent(john, mary).
parent(mary, susan).
parent(john, mark).
parent(mark, alice).

male(john).
male(mark).
female(mary).
female(susan).
female(alice).

father(X, Y) :- parent(X, Y), male(X).
mother(X, Y) :- parent(X, Y), female(X).
""")
    
    if not os.path.exists('lists.pl'):
        with open('lists.pl', 'w') as f:
            f.write("""
% List operations
member(X, [X|_]).
member(X, [_|T]) :- member(X, T).

append([], L, L).
append([H|T], L, [H|R]) :- append(T, L, R).

length([], 0).
length([_|T], N) :- length(T, M), N is M + 1.

sum_list([], 0).
sum_list([H|T], Sum) :- sum_list(T, Rest), Sum is H + Rest.
""")

    print("Example files created: family.pl, lists.pl")
    print("Type 'help' for available commands\n")

    while True:
        try:
            line = input("MiniLogic> ").strip()
        except EOFError:
            print("\nGoodbye!")
            break
        except KeyboardInterrupt:
            print("\nUse 'exit' to quit")
            continue

        line = line.split('%', 1)[0].strip()
        if not line:
            continue

        # Help command
        if line.lower() == 'help':
            print("\nAvailable commands:")
            print("  load <file>          - Load a logic file")
            print("  save <file>          - Save current program")
            print("  save_state <file>    - Save engine state")
            print("  load_state <file>    - Load engine state")
            print("  export <file> <fmt>  - Export to format (prolog/json)")
            print("  clear                - Clear knowledge base")
            print("  trace on/off         - Enable/disable tracing")
            print("  stats on/off         - Enable/disable statistics")
            print("  stats                - Show statistics")
            print("  profile              - Show profiling data")
            print("  explain <goal>       - Explain how goal is resolved")
            print("  validate             - Validate knowledge base")
            print("  stack                - Show call stack")
            print("  type <pred> <types>  - Add type constraints")
            print("  optimize             - Optimize knowledge base")
            print("  show files           - Show loaded files")
            print("  exit                 - Exit the REPL")
            print("\nEnter facts/rules ending with '.' or queries starting with '?-'")
            continue

        if line.lower() == 'exit':
            print("Goodbye!")
            break

        # File I/O commands
        if line.lower().startswith('load '):
            filename = line[5:].strip()
            load_file(engine, filename)
            continue

        if line.lower().startswith('save '):
            parts = line[5:].split()
            filename = parts[0]
            format = 'prolog'
            if len(parts) > 1:
                format = parts[1]
            save_file(engine, filename, format)
            continue

        if line.lower().startswith('save_state '):
            filename = line[11:].strip()
            engine.save_state(filename)
            continue

        if line.lower().startswith('load_state '):
            filename = line[11:].strip()
            engine.load_state(filename)
            continue

        if line.lower().startswith('export '):
            parts = line[7:].split()
            if len(parts) >= 2:
                filename = parts[0]
                format = parts[1]
                export_knowledge(engine, filename, format)
            else:
                print("Usage: export filename format")
            continue

        # Knowledge base management
        if line.lower() == 'clear':
            engine.clear()
            continue

        if line.lower() == 'optimize':
            engine.optimize()
            print("Knowledge base optimized")
            continue

        # Debugging and analysis
        if line.lower() == 'trace on':
            engine.enable_trace(True)
            print("Tracing enabled")
            continue
            
        if line.lower() == 'trace off':
            engine.enable_trace(False)
            print("Tracing disabled")
            continue
            
        if line.lower() == 'stats on':
            engine.enable_stats(True)
            print("Statistics enabled")
            continue
            
        if line.lower() == 'stats off':
            engine.enable_stats(False)
            print("Statistics disabled")
            continue
            
        if line.lower() == 'stats':
            stats = engine.stats()
            print(f"📊 Statistics:")
            print(f"  Facts: {stats['total_facts']}, Rules: {stats['total_rules']}")
            print(f"  Queries: {stats['queries_executed']}, Resolutions: {stats['resolutions_performed']}")
            print(f"  Predicates: {stats['unique_predicates']}")
            if stats['loaded_files']:
                print("  Loaded files:", stats['loaded_files'])
            continue

        if line.lower() == 'profile':
            profile = engine.get_profile()
            print("📈 Profiling data:")
            for pred, data in sorted(profile.items(), key=lambda x: x[1]['time'], reverse=True):
                if data['calls'] > 0:
                    print(f"  {pred}: {data['calls']} calls, {data['time']:.4f}s")
            continue

        if line.lower().startswith('explain '):
            goal = line[8:].strip()
            try:
                engine.explain(goal)
            except Exception as e:
                print(f"Explanation error: {e}")
            continue

        if line.lower() == 'validate':
            errors = engine.validate_knowledge_base()
            if errors:
                print("❌ Validation errors:")
                for error in errors:
                    print(f"  {error}")
            else:
                print("✅ Knowledge base is valid")
            continue

        if line.lower() == 'stack':
            stack = engine.get_call_stack()
            if stack:
                print("📞 Call stack (most recent first):")
                for name, args, depth in reversed(stack):
                    args_str = ", ".join(format_term(a) for a in args)
                    indent = "  " * depth
                    print(f"{indent}{name}({args_str})")
            else:
                print("No active calls")
            continue

        if line.lower().startswith('type '):
            parts = line[5:].split()
            if len(parts) >= 2:
                predicate = parts[0]
                types = parts[1:]
                try:
                    engine.add_type_constraint(predicate, types)
                    print(f"Added type constraints for {predicate}: {types}")
                except Exception as e:
                    print(f"Error: {e}")
            else:
                print("Usage: type predicate type1 type2 ...")
            continue

        if line.lower() == 'show files':
            if engine.loaded_files:
                print("📁 Loaded files:")
                for file in engine.loaded_files:
                    print(f"  {file}")
            else:
                print("No files loaded")
            continue

        # Fact/rule input
        if line.endswith('.'):
            try:
                engine.parse(line, "input")
                engine.optimize()
                print("✅ Fact/rule added.")
            except Exception as e:
                print(f"❌ Parse error: {e}")
            continue

        # Query execution
        if line.startswith('?-'):
            query_text = line[2:].strip()
            if query_text.endswith('.'):
                query_text = query_text[:-1].strip()
            
            # Parse options
            max_solutions = None
            timeout = None
            if 'max' in query_text:
                parts = query_text.split('max')
                query_text = parts[0].strip()
                try:
                    max_solutions = int(parts[1].strip())
                except:
                    pass
            
            try:
                import re
                var_names = re.findall(r'\b[A-Z]\w*\b', query_text)
                var_names = list(set(var_names))
                
                count = 0
                start_time = datetime.now()
                for res in engine.query(query_text, max_solutions, timeout):
                    count += 1
                    if not var_names:
                        print(f"✅ Solution {count}: True")
                    else:
                        solution = {}
                        for var in var_names:
                            if var in res:
                                solution[var] = format_term(substitute(res[var], res))
                        print(f"✅ Solution {count}: {solution}")
                
                duration = (datetime.now() - start_time).total_seconds()
                if count == 0:
                    print("❌ No solutions found.")
                else:
                    print(f"🔍 Found {count} solution(s) in {duration:.3f}s")
                    
            except Exception as e:
                print(f"❌ Query error: {e}")
            continue

        print("❓ Invalid input. Type 'help' for available commands.")

# --- Main execution ---

if __name__ == "__main__":
    # Create example files if they don't exist
    if not os.path.exists('family.pl'):
        with open('family.pl', 'w') as f:
            f.write("""
% Sample family data
parent(john, mary).
parent(mary, susan).
parent(john, mark).
parent(mark, alice).

male(john).
male(mark).
female(mary).
female(susan).
female(alice).

father(X, Y) :- parent(X, Y), male(X).
mother(X, Y) :- parent(X, Y), female(X).
""")
    
    if not os.path.exists('lists.pl'):
        with open('lists.pl', 'w') as f:
            f.write("""
% List operations
member(X, [X|_]).
member(X, [_|T]) :- member(X, T).

append([], L, L).
append([H|T], L, [H|R]) :- append(T, L, R).

length([], 0).
length([_|T], N) :- length(T, M), N is M + 1.

sum_list([], 0).
sum_list([H|T], Sum) :- sum_list(T, Rest), Sum is H + Rest.
""")
    
    # Start the REPL
    repl()