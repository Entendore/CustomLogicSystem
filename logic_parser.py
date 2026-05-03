# logic_parser.py
import re
import logging
from logic_types import split_args, parse_term, is_variable

logger = logging.getLogger("LogicEngine.Parser")

# Operators that act as predicate functors (infix).
# Sorted by length to ensure longer operators (e.g. '=:=') match before shorter ones ('=').
INFIX_OPS = sorted([
    'is', 'ins', '=', '\\=', '<', '>', '>=', '=<', '=:=', '=\=', 
    '#<', '#>', '#=', '#\='
], key=len, reverse=True)

def parse_predicate(text):
    """Parses a predicate string into (name, args_list)."""
    text = text.strip()
    
    # 1. Handle Special Atoms (Cut, Fail, True)
    if text == '!':
        return '!', []
    if text == 'fail':
        return 'fail', []
    if text == 'true':
        return 'true', []

    # 2. Infix Operator Handling
    # We need to find the operator that acts as the predicate functor.
    # This operator must be at "depth 0" (not inside parentheses).
    
    depth = 0
    i = 0
    while i < len(text):
        char = text[i]
        
        # Track parenthesis depth
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        elif depth == 0:
            # Only look for operators at depth 0
            found_op = None
            
            # Check if the substring starting here matches any known operator
            for op in INFIX_OPS:
                if text.startswith(op, i):
                    # Validate boundaries for keyword operators (like 'is')
                    # to avoid matching "is" inside "this".
                    if op.isalpha():
                        # Check char before
                        before_ok = (i == 0 or not text[i-1].isalnum())
                        # Check char after
                        after_idx = i + len(op)
                        after_ok = (after_idx == len(text) or not text[after_idx].isalnum())
                        
                        if before_ok and after_ok:
                            found_op = op
                            break
                    else:
                        # Symbolic operators usually don't need strict boundary checks
                        # but we assume they are distinct tokens.
                        found_op = op
                        break
            
            if found_op:
                # Split text into left and right sides
                lhs_text = text[:i].strip()
                rhs_text = text[i + len(found_op):].strip()
                
                # Parse both sides as terms (handles variables, atoms, and arithmetic nesting)
                arg1 = parse_term(lhs_text)
                arg2 = parse_term(rhs_text)
                
                return found_op, [arg1, arg2]
        
        i += 1

    # 3. Standard Prefix Parsing (e.g., parent(john, mary))
    # Regex matches: name or name(args)
    match = re.match(r'^(\w+)(?:\((.*?)\))?$', text)
    if not match:
        # If no match and not an infix op, it might be just an atom or variable
        if re.match(r'^\w+$', text):
             return text, []
        raise ValueError(f"Invalid predicate syntax: {text}")
    
    name = match.group(1)
    args_str = match.group(2)
    
    if args_str:
        args = [parse_term(a) for a in split_args(args_str)]
    else:
        args = []
        
    return name, args

def expand_dcg_body(body_text, s_in, s_out):
    """Converts DCG body text into a list of logic goals."""
    goals_text = split_args(body_text)
    goals = []
    curr_in = s_in
    
    for i, gt in enumerate(goals_text):
        gt = gt.strip()
        is_last = (i == len(goals_text) - 1)
        curr_out = s_out if is_last else f"_S{i}"
        
        # Terminal: [word]
        if gt.startswith('[') and gt.endswith(']'):
            word = gt[1:-1].strip()
            # Construct goal: =(curr_in, cons(word, curr_out))
            goals.append(('=', (curr_in, ('cons', parse_term(word), curr_out))))
        else:
            # Non-terminal: predicate(Input, Output)
            name, args = parse_predicate(gt)
            goals.append((name, tuple(args) + (curr_in, curr_out)))
        
        curr_in = curr_out
        
    return goals

def parse_program(program, filename="input"):
    """Parses a full program string into facts and rules."""
    facts = {}
    rules = []
    
    lines = program.strip().splitlines()
    buffer = ""
    
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith('%'): continue
        
        buffer += " " + line
        
        # Check for clause terminator
        if buffer.strip().endswith('.'):
            content = buffer.strip()[:-1].strip()
            buffer = ""
            try:
                if '-->' in content:
                    # DCG Handling
                    head, body = content.split('-->', 1)
                    h_name, h_args = parse_predicate(head.strip())
                    if h_args: 
                        raise ValueError("DCG head cannot have pre-existing args")
                    
                    s0 = 'S0'
                    s = 'S'
                    goals = expand_dcg_body(body.strip(), s0, s)
                    rules.append((h_name, [s0, s], goals))
                    
                elif ':-' in content:
                    # Rule Handling
                    head, body = content.split(':-', 1)
                    h_name, h_args = parse_predicate(head.strip())
                    b_parts = [parse_predicate(g.strip()) for g in split_args(body)]
                    rules.append((h_name, h_args, b_parts))
                else:
                    # Fact Handling
                    name, args = parse_predicate(content)
                    if name not in facts: facts[name] = []
                    facts[name].append(tuple(args))
            except Exception as e:
                logger.error(f"Parse error near line {i}: {e}")
                raise
                
    return facts, rules