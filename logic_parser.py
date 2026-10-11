# logic_parser.py
import re
import logging
from logic_types import parse_term, split_args, Compound, Atom, Var, Cons, Nil

logger = logging.getLogger("LogicEngine.Parser")

def parse_predicate(text, var_table=None):
    text = text.strip().rstrip('.')
    term = parse_term(text, var_table)
    if isinstance(term, Compound):
        return term.functor, list(term.args)
    elif isinstance(term, (Atom, Var)):
        return term.name, []
    else:
        raise ValueError(f"Invalid predicate: {text}")

def flatten_body(term):
    if not term or (isinstance(term, Atom) and term.name == 'true'):
        return []
    if not isinstance(term, Compound):
        return [term]
        
    if term.functor == ',':
        return flatten_body(term.args[0]) + flatten_body(term.args[1])
    elif term.functor == ';':
        left = flatten_body(term.args[0])
        right = flatten_body(term.args[1])
        if len(left) == 1 and isinstance(left[0], Compound) and left[0].functor == '->':
            return [Compound(';', (left[0], right[0] if len(right) == 1 else Compound(',', tuple(right))))]
        left_g = left[0] if len(left) == 1 else Compound(',', tuple(left))
        right_g = right[0] if len(right) == 1 else Compound(',', tuple(right))
        return [Compound(';', (left_g, right_g))]
    elif term.functor == '->':
        cond = flatten_body(term.args[0])
        then = flatten_body(term.args[1])
        cond_g = cond[0] if len(cond) == 1 else Compound(',', tuple(cond))
        then_g = then[0] if len(then) == 1 else Compound(',', tuple(then))
        return [Compound('->', (cond_g, then_g))]
    else:
        return [term]

def parse_program(program, filename="input"):
    facts, rules = {}, []
    text = re.sub(r'%.*', '', program.strip())
    
    clauses, depth, start = [], 0, 0
    for i, char in enumerate(text):
        if char in '([': depth += 1
        elif char in ')]': depth -= 1
        elif char == '.' and depth == 0:
            # Prevent splitting on decimal points for floats (e.g., 3.14)
            if i > 0 and i < len(text) - 1 and text[i-1].isdigit() and text[i+1].isdigit():
                continue
            c = text[start:i].strip()
            if c: clauses.append(c)
            start = i + 1
            
    for content in clauses:
        try:
            if '-->' in content:
                # Create a var_table per clause for variable sharing
                var_table = {}
                head, body = content.split('-->', 1)
                h_name, h_args = parse_predicate(head.strip(), var_table)
                
                # Use underscore-prefixed names for DCG internal variables
                # to avoid conflicts with user variables and to mark them
                # as anonymous/singleton for output filtering.
                s_in, s_out = Var('_S0'), Var('_Sn')
                goals, curr_in = [], s_in
                
                body_terms = split_args(body.strip())
                for i, gt in enumerate(body_terms):
                    gt = gt.strip()
                    is_last = (i == len(body_terms) - 1)
                    curr_out = s_out if is_last else Var(f"_S{i}")
                    
                    if gt.startswith('['):
                        # Parse whole list like [the, a] correctly
                        list_term = parse_term(gt, var_table)
                        def append_tail(lst, tail):
                            if isinstance(lst, Nil): return tail
                            if isinstance(lst, Var): return tail # Open list support
                            if isinstance(lst, Cons): return Cons(lst.head, append_tail(lst.tail, tail))
                            raise ValueError(f"Invalid list term in DCG: {gt}")
                        full_list = append_tail(list_term, curr_out)
                        goals.append(Compound('=', (curr_in, full_list)))
                    else:
                        p = parse_term(gt, var_table)
                        g_name = p.name if isinstance(p, (Atom, Var)) else p.functor
                        g_args = () if isinstance(p, (Atom, Var)) else p.args
                        goals.append(Compound(g_name, g_args + (curr_in, curr_out)))
                    curr_in = curr_out
                rules.append((h_name, tuple(h_args) + (s_in, s_out), goals))
                
            elif ':-' in content:
                # Create a var_table per clause for variable sharing
                var_table = {}
                head, body = content.split(':-', 1)
                h_name, h_args = parse_predicate(head.strip(), var_table)
                rules.append((h_name, tuple(h_args), flatten_body(parse_term(body.strip(), var_table))))
            else:
                var_table = {}
                name, args = parse_predicate(content, var_table)
                if name not in facts: facts[name] = []
                facts[name].append(tuple(args))
        except Exception as e:
            logger.error(f"Parse error in '{content}': {e}")
            raise
    return facts, rules