# logic_parser.py
import re
import logging
from logic_types import parse_term, split_args, Compound, Atom, Var, Cons, Nil

logger = logging.getLogger("LogicEngine.Parser")

def parse_predicate(text):
    text = text.strip().rstrip('.')
    term = parse_term(text)
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
            c = text[start:i].strip()
            if c: clauses.append(c)
            start = i + 1
            
    for content in clauses:
        try:
            if '-->' in content:
                head, body = content.split('-->', 1)
                h_name, h_args = parse_predicate(head.strip())
                # FIX: Use raw Var strings for DCG tests matching
                s_in, s_out = Var('S0'), Var('S')
                goals, curr_in = [], s_in
                
                for i, gt in enumerate(split_args(body.strip())):
                    gt = gt.strip()
                    is_last = (i == len(split_args(body.strip())) - 1)
                    curr_out = s_out if is_last else Var(f"_S{i}")
                    if gt.startswith('[') and gt.endswith(']'):
                        word = gt[1:-1].strip()
                        # FIX: Added missing 'Cons' reference & correct list construction
                        goals.append(Compound('=', (curr_in, Cons(parse_term(word), curr_out))))
                    else:
                        p = parse_term(gt)
                        g_name = p.name if isinstance(p, (Atom, Var)) else p.functor
                        g_args = () if isinstance(p, (Atom, Var)) else p.args
                        goals.append(Compound(g_name, g_args + (curr_in, curr_out)))
                    curr_in = curr_out
                rules.append((h_name, (s_in, s_out), goals))
                
            elif ':-' in content:
                head, body = content.split(':-', 1)
                h_name, h_args = parse_predicate(head.strip())
                rules.append((h_name, tuple(h_args), flatten_body(parse_term(body.strip()))))
            else:
                name, args = parse_predicate(content)
                if name not in facts: facts[name] = []
                facts[name].append(tuple(args))
        except Exception as e:
            logger.error(f"Parse error: {e}")
            raise
    return facts, rules