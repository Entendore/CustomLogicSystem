# logic_types.py
import re
import logging

logger = logging.getLogger("LogicEngine.Types")

# --- Exception & Context ---

class CutException(Exception):
    pass

class ResolveContext:
    def __init__(self):
        self.cut = False

# --- Parsing Helpers ---

def split_args(text):
    """Splits arguments by comma, respecting nested parenthesis."""
    if not text: return []
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
    # Numbers
    if text.replace('.', '', 1).replace('-', '', 1).isdigit() and text.count('.') <= 1:
        return float(text) if '.' in text else int(text)
    # Strings
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    # List Syntax
    if text.startswith('[') and text.endswith(']'):
        return parse_list(text[1:-1].strip())
    # Compound Terms
    match = re.match(r'^(\w+)\((.*)\)$', text)
    if match:
        name = match.group(1)
        args = split_args(match.group(2))
        return (name, tuple(parse_term(arg) for arg in args))
    # Atom/Variable
    return text

def parse_list(text):
    if not text:
        return ('nil',)
    if '|' in text:
        head_text, tail_text = map(str.strip, text.split('|', 1))
        return ('cons', parse_term(head_text), parse_term(tail_text))
    items = split_args(text)
    if not items:
        return ('nil',)
    result = ('nil',)
    for item in reversed(items):
        result = ('cons', parse_term(item), result)
    return result

def format_term(term):
    if isinstance(term, (int, float)):
        return str(term)
    if isinstance(term, str):
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
    return str(term)

# --- Logic Helpers ---

def is_variable(x):
    return isinstance(x, str) and x and (x[0].isupper() or x[0] == '_')

def substitute(term, env):
    if isinstance(term, str):
        return env.get(term, term)
    if isinstance(term, tuple):
        if len(term) == 0: return term
        return (term[0],) + tuple(substitute(t, env) for t in term[1:])
    return term

def deref(term, env):
    while isinstance(term, str) and term in env:
        term = env[term]
    return term

def occurs_check(var, term, env):
    term = deref(term, env)
    if var == term: return True
    if isinstance(term, tuple):
        return any(occurs_check(var, t, env) for t in term[1:])
    return False

def unify(x, y, env):
    env = env.copy()
    x = deref(x, env)
    y = deref(y, env)

    if x == y: return env

    if is_variable(x):
        if occurs_check(x, y, env): return None
        env[x] = y
        return env

    if is_variable(y):
        if occurs_check(y, x, env): return None
        env[y] = x
        return env

    # Handle Unification of Sequences (Lists vs Tuples)
    if isinstance(x, (list, tuple)) and isinstance(y, (list, tuple)):
        if len(x) != len(y): return None
        
        for a, b in zip(x, y):
            res = unify(a, b, env)
            if res is None: return None
            env = res
        return env

    return None

# --- Variable Renaming ---

_var_counter = 0

def rename_variables(term, suffix):
    """
    Renames variables in a term to avoid conflicts during rule application.
    e.g., X becomes X_1, Y becomes Y_1.
    """
    if is_variable(term):
        return f"{term}{suffix}"
    if isinstance(term, tuple):
        return (term[0],) + tuple(rename_variables(t, suffix) for t in term[1:])
    if isinstance(term, list):
        return [rename_variables(t, suffix) for t in term]
    return term