import re
from collections import defaultdict

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

    def _resolve(self, name, args, env, context):
        if context.cut:
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
                query_text = query_text[:-1].strip()  # remove trailing dot
            try:
                results = engine.query(query_text)
                count = 0
                # Detect variables in query to show bindings
                has_vars = any(is_variable(v) for v in re.findall(r'\b\w+\b', query_text))
                for res in results:
                    if not has_vars:
                        print("True")
                        count += 1
                        break
                    filtered = {k: substitute(v, res) for k, v in res.items() if is_variable(k)}
                    if filtered:
                        print(filtered)
                        count += 1
                if count == 0:
                    print("False")
            except Exception as e:
                print(f"Query error: {e}")
            continue

        print("Invalid input. Enter facts/rules ending with '.', queries starting with '?-', or commands (load/save/exit).")

if __name__ == "__main__":
    repl()
