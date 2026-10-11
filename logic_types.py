# logic_types.py
import logging
import re

logger = logging.getLogger("LogicEngine.Types")

# --- AST Data Structures ---
class Term:
    pass

class Atom(Term):
    def __init__(self, name):
        self.name = name
    def __eq__(self, other): 
        return isinstance(other, Atom) and self.name == other.name
    def __hash__(self): return hash(('Atom', self.name))
    def __repr__(self): return self.name

class Var(Term):
    _id_counter = 0
    def __init__(self, name):
        self.name = name
        self._id = Var._id_counter
        Var._id_counter += 1
        
    def __eq__(self, other): 
        return isinstance(other, Var) and self._id == other._id
    def __hash__(self): return hash(('Var', self._id))
    def __repr__(self): return self.name

class Num(Term):
    def __init__(self, val):
        self.val = val
    def __eq__(self, other): 
        return isinstance(other, Num) and self.val == other.val
    def __hash__(self): return hash(('Num', self.val))
    def __repr__(self): return str(self.val)

class Cons(Term):
    def __init__(self, head, tail):
        self.head = head
        self.tail = tail
    def __eq__(self, other): 
        return isinstance(other, Cons) and self.head == other.head and self.tail == other.tail
    def __hash__(self): return hash(('Cons', self.head, self.tail))
    def __repr__(self): return f"[{format_term(self)}]"

class Nil(Term):
    def __eq__(self, other): 
        return isinstance(other, Nil)
    def __hash__(self): return hash('Nil')
    def __repr__(self): return "[]"

class Compound(Term):
    def __init__(self, functor, args):
        self.functor = functor
        self.args = tuple(args)
    def __eq__(self, other): 
        return isinstance(other, Compound) and self.functor == other.functor and self.args == other.args
    def __hash__(self): return hash(('Compound', self.functor, self.args))
    def __repr__(self): return f"{format_term(self)}"

# --- Context ---
class ResolveContext:
    def __init__(self):
        self.cut = False
        self._cut_scopes = []
    def push_cut_scope(self):
        self._cut_scopes.append(self.cut)
        self.cut = False
    def pop_cut_scope(self):
        cut_occurred = self.cut
        self.cut = self._cut_scopes.pop()
        return cut_occurred

# --- Helpers ---
def is_variable(term):
    return isinstance(term, Var)

def deref(term, env):
    while isinstance(term, Var) and term in env:
        term = env[term]
    return term

def format_term(term):
    if isinstance(term, Atom): return term.name
    if isinstance(term, Var): return term.name
    if isinstance(term, Num): return str(term.val)
    if isinstance(term, Nil): return "[]"
    if isinstance(term, Cons):
        head = format_term(term.head)
        tail = term.tail
        if isinstance(tail, Nil): return f"[{head}]"
        elif isinstance(tail, Cons): return f"[{head}, {format_term(tail)[1:-1]}]"
        else: return f"[{head}|{format_term(tail)}]"
    if isinstance(term, Compound):
        if term.functor in OP_INFO and len(term.args) == 2:
            return f"({format_term(term.args[0])} {term.functor} {format_term(term.args[1])})"
        args = ", ".join(format_term(a) for a in term.args)
        return f"{term.functor}({args})"
    if isinstance(term, (tuple, list)):
        return f"({', '.join(format_term(a) for a in term)})"
    return str(term)

def substitute(term, env):
    if isinstance(term, Var):
        return env.get(term, term)
    if isinstance(term, Compound):
        return Compound(term.functor, tuple(substitute(a, env) for a in term.args))
    if isinstance(term, Cons):
        return Cons(substitute(term.head, env), substitute(term.tail, env))
    if isinstance(term, (tuple, list)):
        return tuple(substitute(a, env) for a in term)
    return term

def occurs_check(var, term, env):
    term = deref(term, env)
    if var == term: return True
    if isinstance(term, Compound):
        return any(occurs_check(var, a, env) for a in term.args)
    if isinstance(term, Cons):
        return occurs_check(var, term.head, env) or occurs_check(var, term.tail, env)
    if isinstance(term, (tuple, list)):
        return any(occurs_check(var, a, env) for a in term)
    return False

def unify(x, y, env):
    env = env.copy()
    x = deref(x, env)
    y = deref(y, env)

    if x == y: return env
    if isinstance(x, Var):
        if occurs_check(x, y, env): return None
        env[x] = y
        return env
    if isinstance(y, Var):
        if occurs_check(y, x, env): return None
        env[y] = x
        return env
    if isinstance(x, Compound) and isinstance(y, Compound):
        if x.functor != y.functor or len(x.args) != len(y.args): return None
        for a, b in zip(x.args, y.args):
            res = unify(a, b, env)
            if res is None: return None
            env = res
        return env
    if isinstance(x, Cons) and isinstance(y, Cons):
        res = unify(x.head, y.head, env)
        if res is None: return None
        return unify(x.tail, y.tail, res)
    if isinstance(x, Nil) and isinstance(y, Nil): return env
    if isinstance(x, (tuple, list)) and isinstance(y, (tuple, list)):
        if len(x) != len(y): return None
        for a, b in zip(x, y):
            res = unify(a, b, env)
            if res is None: return None
            env = res
        return env
    return None

# FIX: rename_variables now uses a rename_table to ensure the same source Var
# always maps to the same renamed Var, preserving variable sharing within a rule.
def rename_variables(term, suffix, rename_table=None):
    if rename_table is None:
        rename_table = {}
    if isinstance(term, Var):
        if term in rename_table:
            return rename_table[term]
        new_var = Var(f"{term.name}{suffix}")
        rename_table[term] = new_var
        return new_var
    if isinstance(term, Compound):
        return Compound(term.functor, tuple(rename_variables(a, suffix, rename_table) for a in term.args))
    if isinstance(term, Cons):
        return Cons(rename_variables(term.head, suffix, rename_table), rename_variables(term.tail, suffix, rename_table))
    if isinstance(term, (tuple, list)):
        return tuple(rename_variables(a, suffix, rename_table) for a in term)
    return term

# --- Parser ---
OP_INFO = {
    ';': (10, 'r'), ',': (20, 'r'), '->': (25, 'r'),
    '=': (40, 'r'), '\\=': (40, 'r'), 'is': (40, 'r'),
    '=:=': (40, 'r'), '=\=': (40, 'r'),
    '<': (40, 'r'), '>': (40, 'r'), '=<': (40, 'r'), '>=': (40, 'r'),
    '+': (50, 'l'), '-': (50, 'l'),
    '*': (60, 'l'), '/': (60, 'l'), '//': (60, 'l'), 'mod': (60, 'l'),
    '^': (70, 'r'),
}

def split_args(text):
    if not text: return []
    args, depth, start = [], 0, 0
    for i, c in enumerate(text):
        if c == ',' and depth == 0:
            args.append(text[start:i].strip())
            start = i + 1
        elif c in '([': depth += 1
        elif c in ')]': depth -= 1
    args.append(text[start:].strip())
    return [a for a in args if a]

# FIX: parse_term now accepts var_table to share variables within a clause.
# When the same variable name appears multiple times, it reuses the same Var object.
def parse_term(text, var_table=None):
    text = text.strip()
    if not text:
        raise ValueError("Empty term")

    if text.startswith('(') and text.endswith(')'):
        d, m = 0, True
        for i, c in enumerate(text):
            if c == '(': d += 1
            elif c == ')': d -= 1
            if d == 0 and i < len(text) - 1: m = False; break
        if m: return parse_term(text[1:-1], var_table)

    try:
        if '.' in text:
            return Num(float(text))
        return Num(int(text))
    except ValueError: 
        pass

    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return Atom(text[1:-1])

    if text.startswith('[') and text.endswith(']'):
        return parse_list(text[1:-1].strip(), var_table)

    if text.startswith('-') and not text.startswith('->'):
        val = parse_term(text[1:].strip(), var_table)
        if isinstance(val, Num): return Num(-val.val)
        return Compound('-', (val,))

    candidates, depth, i = [], 0, 0
    while i < len(text):
        c = text[i]
        if c in '([': depth += 1
        elif c in ')]': depth -= 1
        elif depth == 0:
            matching_ops = [op for op in OP_INFO if text.startswith(op, i)]
            if matching_ops:
                op = max(matching_ops, key=len)
                if op.isalpha():
                    b_ok = (i == 0 or not text[i-1].isalnum())
                    a_idx = i + len(op)
                    a_ok = (a_idx == len(text) or not text[a_idx].isalnum())
                    if b_ok and a_ok:
                        candidates.append((i, op, OP_INFO[op][0], OP_INFO[op][1]))
                else:
                    candidates.append((i, op, OP_INFO[op][0], OP_INFO[op][1]))
        i += 1

    if candidates:
        min_p = min(c[2] for c in candidates)
        lows = [c for c in candidates if c[2] == min_p]
        t = lows[-1] if lows[0][3] == 'l' else lows[0]
        idx, op, _, _ = t
        lhs = parse_term(text[:idx].strip(), var_table)
        rhs = parse_term(text[idx+len(op):].strip(), var_table)
        return Compound(op, (lhs, rhs))

    match = re.match(r'^(\w+)\((.*)\)$', text)
    if match:
        return Compound(match.group(1), tuple(parse_term(a, var_table) for a in split_args(match.group(2))))
    
    # FIX: Variable sharing - reuse Var objects with the same name within a clause
    if text[0].isupper() or text[0] == '_': 
        if var_table is not None and text in var_table:
            return var_table[text]
        v = Var(text)
        if var_table is not None:
            var_table[text] = v
        return v
    return Atom(text)

# FIX: parse_list now accepts and passes var_table
def parse_list(text, var_table=None):
    if not text: return Nil()
    if '|' in text:
        parts = text.split('|', 1)
        heads = [parse_term(h, var_table) for h in split_args(parts[0])]
        tail = parse_term(parts[1].strip(), var_table)
        result = tail
        for h in reversed(heads): result = Cons(h, result)
        return result
    items = [parse_term(i, var_table) for i in split_args(text)]
    result = Nil()
    for i in reversed(items): result = Cons(i, result)
    return result