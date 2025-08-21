import re
from collections import defaultdict
import pickle
import json

# --- Parsing helpers ---

def split_args(text):
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
    text = text.strip()
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
    if isinstance(term, tuple):
        if term[0] == 'nil':
            return '[]'
        if term[0] == 'cons':
            head = format_term(term[1])
            tail = format_term(term[2])
            if tail == '[]':
                return f"[{head}]"
            else:
                return f"[{head}|{tail}]"
        name = term[0]
        args = ', '.join(format_term(a) for a in term[1:])
        return f"{name}({args})"
    else:
        return str(term)

def is_variable(x):
    return isinstance(x, str) and x and x[0].isupper()

# --- Substitution helper ---

def substitute(term, env):
    if isinstance(term, str):
        return env.get(term, term)
    if isinstance(term, tuple):
        return (term[0], tuple(substitute(t, env) for t in term[1:]))
    return term

# --- Unification ---

def unify(x, y, env):
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
    term = deref(term, env)
    if var == term:
        return True
    if isinstance(term, tuple):
        return any(occurs_check(var, t, env) for t in term[1:])
    return False

def deref(term, env):
    while isinstance(term, str) and term in env:
        term = env[term]
    return term

# --- Cut support ---

class ResolveContext:
    def __init__(self):
        self.cut = False

# --- Logic Engine ---

class LogicEngine:
    def __init__(self):
        self.facts = defaultdict(list)  # predicate -> list of tuples
        self.rules = []  # (head_name, head_args, body_parts)
        self.trace_enabled = False

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
        
        # Remove facts
        if name in self.facts:
            self.facts[name] = [fact for fact in self.facts[name] 
                               if not all(unify(pattern_arg, fact_arg, {}) 
                                        for pattern_arg, fact_arg in zip(args, fact))]
        
        # Remove rules
        self.rules = [rule for rule in self.rules 
                     if not (rule[0] == name and 
                            all(unify(pattern_arg, rule_arg, {})
                               for pattern_arg, rule_arg in zip(args, rule[1])))]
    
    def query(self, q, max_solutions=None, timeout=None):
        """Enhanced query with limits"""
        import time
        start_time = time.time()
        solutions_found = 0
        
        name, args = self._parse_predicate(q)
        context = ResolveContext()
        
        for result in self._resolve(name, args, {}, context):
            if timeout and time.time() - start_time > timeout:
                print("Query timeout reached")
                break
            
            solutions_found += 1
            yield result
            
            if max_solutions and solutions_found >= max_solutions:
                break

    def stats(self):
        """Return statistics about the knowledge base"""
        total_facts = sum(len(facts) for facts in self.facts.values())
        total_rules = len(self.rules)
        predicates = list(self.facts.keys()) + [rule[0] for rule in self.rules]
        
        return {
            'total_facts': total_facts,
            'total_rules': total_rules,
            'unique_predicates': len(set(predicates)),
            'predicate_counts': {pred: len(self.facts.get(pred, [])) 
                                for pred in set(predicates)}
        }

    def save_state(self, filename):
        """Save entire engine state to file"""
        state = {
            'facts': dict(self.facts),
            'rules': self.rules,
            'constraints': self.constraints
        }
        with open(filename, 'wb') as f:
            pickle.dump(state, f)
    
    def load_state(self, filename):
        """Load engine state from file"""
        with open(filename, 'rb') as f:
            state = pickle.load(f)
        self.facts = defaultdict(list, state['facts'])
        self.rules = state['rules']
        self.constraints = state['constraints']
        self.memo.clear()

    def enable_trace(self, enabled=True):
        self.trace_enabled = enabled

    def parse(self, program):
        for line in program.strip().splitlines():
            line = line.strip()
            if not line or line.startswith('%'):
                continue
            if not line.endswith('.'):
                raise ValueError(f"Line must end with '.': {line}")
            line = line[:-1].strip()
            if ':-' in line:
                self._parse_rule(line)
            else:
                self._parse_fact(line)

    def _parse_fact(self, line):
        name, args = self._parse_predicate(line)
        self.facts[name].append(tuple(args))

    def _parse_rule(self, line):
        head, body = map(str.strip, line.split(':-'))
        head_name, head_args = self._parse_predicate(head)
        body_parts = [self._parse_predicate(part.strip()) for part in split_args(body)]
        self.rules.append((head_name, head_args, body_parts))

    def _parse_predicate(self, text):
        text = text.strip()
        # Allow predicates with no arguments (e.g. cut)
        match = re.match(r'^(\w+)(?:\((.*?)\))?$', text)
        if not match:
            raise ValueError(f"Invalid predicate: {text}")
        name = match.group(1)
        args_text = match.group(2)
        if args_text is None:
            # zero-argument predicate
            return name, []
        args = split_args(args_text)
        parsed_args = [parse_term(arg) for arg in args]
        return name, parsed_args

    def query(self, q):
        name, args = self._parse_predicate(q)
        context = ResolveContext()
        results = self._resolve(name, args, {}, context)
        return results

    def _resolve(self, name, args, env, context, depth=0):
        if self.trace_enabled:
            indent = "  " * depth
            args_str = ", ".join(format_term(a) for a in args)
            print(f"{indent}TRY: {name}({args_str})")

        if context.cut:
            return

        if name == 'findall' and len(args) == 3:
            template = args[0]
            goal = args[1]  # This should be a compound term like ('member', ...)
            output_var = args[2]
            
            if isinstance(goal, tuple) and len(goal) >= 1:
                solutions = []
                for result_env in self._resolve(goal[0], goal[1:], env.copy(), context):
                    solved_template = substitute(template, result_env)
                    solutions.append(solved_template)
                
                # Convert solutions to a list
                result_list = ('nil',)
                for solution in reversed(solutions):
                    result_list = ('cons', solution, result_list)
                
                new_env = unify(output_var, result_list, env.copy())
                if new_env is not None:
                    yield new_env
            return

        # Built-ins
        if name == 'true' and len(args) == 0:
            yield env
            return
        if name == 'fail' and len(args) == 0:
            return
        if name == 'eq' and len(args) == 2:
            if unify(args[0], args[1], env) is not None:
                yield env
            return
        if name == 'write' and len(args) == 1:
            val = substitute(args[0], env)
            print(format_term(val))
            yield env
            return
        
        if name == 'maplist' and len(args) >= 2:
            goal = args[0]
            input_list = substitute(args[1], env)
            output_list = args[2] if len(args) > 2 else None
            
            def apply_goal_to_list(lst, goal_template):
                if lst == ('nil',):
                    return ('nil',)
                if isinstance(lst, tuple) and lst[0] == 'cons':
                    head_result = list(self._resolve(goal_template[0], 
                                                goal_template[1:] + [lst[1]], 
                                                env.copy(), context))[0]
                    if head_result:
                        tail_result = apply_goal_to_list(lst[2], goal_template)
                        return ('cons', substitute(goal_template[-1], head_result), tail_result)
                return None
            
            result = apply_goal_to_list(input_list, goal)
            if result and output_list:
                new_env = unify(output_list, result, env.copy())
                if new_env is not None:
                    yield new_env
            return

        if name == 'is' and len(args) == 2:
            left = substitute(args[0], env)
            right = substitute(args[1], env)
            # Simple arithmetic evaluation
            if isinstance(right, str) and right.replace('.', '').isdigit():
                result = float(right) if '.' in right else int(right)
                new_env = unify(left, result, env.copy())
                if new_env is not None:
                    yield new_env
            return

        if name == 'lt' and len(args) == 2:  # less than
            left = substitute(args[0], env)
            right = substitute(args[1], env)
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                if left < right:
                    yield env
            return

        if name == 'gt' and len(args) == 2:  # greater than
            left = substitute(args[0], env)
            right = substitute(args[1], env)
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                if left > right:
                    yield env
            return
        
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
            return

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
            return

        # Negation: not(P)
        if name == 'not' and len(args) == 1:
            neg_pred = args[0]
            for _ in self._resolve(neg_pred[0], neg_pred[1:], env.copy(), context):
                return
            yield env
            return

        # Cut operator: cut/0
        if name == 'cut' and len(args) == 0:
            context.cut = True
            yield env
            return

        # Facts
        for fact in self.facts.get(name, []):
            if context.cut:
                return
            match = unify(args, fact, env)
            if match is not None:
                yield match

        # Rules
        for rule_name, rule_head, rule_body in self.rules:
            if context.cut:
                return
            if rule_name != name or len(rule_head) != len(args):
                continue
            head_match = unify(rule_head, args, env)
            if head_match is None:
                continue
            yield from self._resolve_body(rule_body, head_match, context)

        if self.trace_enabled and result_found:
            print(f"{indent}SUCCESS: {name}({args_str})")

    def _resolve_body(self, body, env, context):
        if not body or context.cut:
            yield env
            return
        name, args = body[0]
        rest = body[1:]

        # Cut in body handled here too
        if name == 'cut' and len(args) == 0:
            context.cut = True
            yield env
            return

        for match in self._resolve(name, args, env.copy(), context):
            yield from self._resolve_body(rest, match, context)

# --- File I/O ---

def load_file(engine, filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    engine.parse(content)

def save_file(engine, filepath):
    with open(filepath, 'w') as f:
        for pred, facts in engine.facts.items():
            for fact in facts:
                args_str = ', '.join(format_term(a) for a in fact)
                f.write(f"{pred}({args_str}).\n")
        for head_name, head_args, body_parts in engine.rules:
            head_str = f"{head_name}({', '.join(format_term(a) for a in head_args)})"
            body_str = ', '.join(f"{n}({', '.join(format_term(a) for a in args)})" for n, args in body_parts)
            f.write(f"{head_str} :- {body_str}.\n")

# --- REPL ---

def repl():
    print("MiniLogic REPL")
    print("Commands:")
    print("  exit                - quit")
    print("  load filename       - load facts/rules from file")
    print("  save filename       - save current program to file")
    print("  facts/rules end with '.'")
    print("  queries start with '?-'")
    engine = LogicEngine()

    preload = """
    parent(john, mary).
    parent(mary, susan).
    parent(john, mark).
    parent(mark, alice).
    
    ancestor(X, Y) :- parent(X, Y).
    ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).
    
    no_parent(X) :- not(parent(_, X)).
    
    member(X, [X|_]).
    member(X, [_|T]) :- member(X, T).
    
    example_cut(X) :- first_case(X), cut, second_case(X).
    first_case(a).
    first_case(b).
    second_case(c).

    % Using built-in write predicate to print something
    print_hello :- write(hello_world).

    % Check equality with eq/2
    equal_example(X) :- eq(X, alice).


    Sudoku solver example
sudoku(Rows) :- 
    length(Rows, 9),
    maplist(same_length(Rows), Rows),
    maplist(fd_domain(1, 9), Rows),
    maplist(fd_all_different, Rows),
    transpose(Rows, Columns),
    maplist(fd_all_different, Columns),
    Rows = [A,B,C,D,E,F,G,H,I],
    blocks(A, B, C), blocks(D, E, F), blocks(G, H, I).

blocks([], [], []).
blocks([A,B,C|Bs1], [D,E,F|Bs2], [G,H,I|Bs3]) :-
    fd_all_different([A,B,C,D,E,F,G,H,I]),
    blocks(Bs1, Bs2, Bs3).

fd_domain(Min, Max, Var) :- between(Min, Max, Var).
fd_all_different(List) :- is_set(List).

between(Min, Max, Min) :- Min =< Max.
between(Min, Max, Val) :- Min < Max, Next is Min + 1, between(Next, Max, Val).

transpose([], []).
transpose([Row|Rows], Cols) :- transpose(Rows, Rest), zip(Row, Rest, Cols).

zip([], [], []).
zip([X|Xs], [Y|Ys], [(X,Y)|Zs]) :- zip(Xs, Ys, Zs).

is_set([]).
is_set([H|T]) :- not(member(H, T)), is_set(T).
    """

    engine.parse(preload)

    while True:
        try:
            line = input("MiniLogic> ").strip()
        except EOFError:
            print("\nGoodbye!")
            break

        line = line.split('%', 1)[0].strip()
        if not line:
            continue
        
        if line.lower() == 'trace on':
            engine.enable_trace(True)
            print("Tracing enabled")
            continue
            
        if line.lower() == 'trace off':
            engine.enable_trace(False)
            print("Tracing disabled")
            continue
            
        if line.lower() == 'show facts':
            for pred, facts in engine.facts.items():
                for fact in facts:
                    args_str = ', '.join(format_term(a) for a in fact)
                    print(f"{pred}({args_str}).")
            continue
            
        if line.lower() == 'show rules':
            for head_name, head_args, body_parts in engine.rules:
                head_str = f"{head_name}({', '.join(format_term(a) for a in head_args)})"
                body_str = ', '.join(f"{n}({', '.join(format_term(a) for a in args)})" for n, args in body_parts)
                print(f"{head_str} :- {body_str}.")
            continue

        if line.lower() == 'exit':
            print("Goodbye!")
            break

        if line.startswith('load '):
            filename = line[5:].strip()
            try:
                load_file(engine, filename)
                print(f"Loaded from {filename}")
            except Exception as e:
                print(f"Load error: {e}")
            continue

        if line.startswith('save '):
            filename = line[5:].strip()
            try:
                save_file(engine, filename)
                print(f"Saved to {filename}")
            except Exception as e:
                print(f"Save error: {e}")
            continue

        if line.endswith('.'):
            try:
                engine.parse(line)
                print("Fact/rule added.")
            except Exception as e:
                print(f"Parse error: {e}")
            continue

        if line.startswith('?-'):
            query_text = line[2:].strip()
            if query_text.endswith('.'):
                query_text = query_text[:-1].strip()
            try:
                results = engine.query(query_text)
                count = 0
                
                # Extract variable names from query for nicer output
                import re
                var_names = re.findall(r'\b[A-Z]\w*\b', query_text)
                var_names = list(set(var_names))  # Remove duplicates
                
                for res in results:
                    count += 1
                    if not var_names:
                        print(f"Solution {count}: True")
                    else:
                        solution = {}
                        for var in var_names:
                            if var in res:
                                solution[var] = format_term(substitute(res[var], res))
                        print(f"Solution {count}: {solution}")
                
                if count == 0:
                    print("No solutions found.")
                else:
                    print(f"Found {count} solution(s).")
                    
            except Exception as e:
                print(f"Query error: {e}")
            continue

        print("Invalid input. Enter facts/rules ending with '.', queries starting with '?-', or commands (load/save/exit).")

if __name__ == "__main__":
    repl()
