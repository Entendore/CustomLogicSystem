# logic_engine.py
import logging
from collections import defaultdict
from logic_types import (substitute, unify, is_variable, deref, ResolveContext, 
                         rename_variables, Atom, Var, Num, format_term)
from logic_features import BuiltinHandler
from logic_parser import parse_program

logging.raiseExceptions = False
logger = logging.getLogger("LogicEngine")

class LogicEngine:
    def __init__(self):
        self.facts = defaultdict(list)
        self.rules = []
        self.indexed_facts = defaultdict(lambda: defaultdict(list))
        self.compiled_rules = defaultdict(list)
        self.query_count = 0
        self.max_depth = 1000
        self.trace_enabled = False
        self.tabled_predicates = set()
        self.memo_table = defaultdict(list)
        self.builtin_handler = BuiltinHandler(self)
        self._var_counter = 0

    def parse(self, program, filename="input"):
        new_facts, new_rules = parse_program(program, filename)
        self.facts.clear()
        self.rules.clear()
        for name, fact_list in new_facts.items():
            self.facts[name].extend(fact_list)
        self.rules.extend(new_rules)

    def optimize(self):
        logger.info("Optimizing knowledge base...")
        self.indexed_facts.clear()
        self.compiled_rules.clear()
        for pred, facts in self.facts.items():
            for f in facts:
                if f and isinstance(f[0], Atom) and not is_variable(f[0]):
                    self.indexed_facts[pred][f[0].name].append(f)
        for r in self.rules:
            self.compiled_rules[(r[0], len(r[1]))].append(r)

    def clear(self):
        self.facts.clear()
        self.rules.clear()
        self.builtin_handler.reset_constraints()
        self.memo_table.clear()
        logger.info("Engine cleared.")

    def query(self, query_str, max_solutions=100):
        self.query_count += 1
        self.builtin_handler.reset_constraints()
        from logic_parser import parse_predicate
        q_name, q_args = parse_predicate(query_str)
        context = ResolveContext()
        count = 0
        for sol in self._resolve(q_name, tuple(q_args), {}, context, 0):
            final_sol = {}
            for a in q_args:
                if is_variable(a):
                    val = deref(a, sol)
                    # FIX: Unpack primitive values instead of returning AST nodes
                    if isinstance(val, Num): 
                        final_sol[a.name] = val.val
                    elif isinstance(val, Atom):
                        final_sol[a.name] = val.name
                    elif isinstance(val, Var):
                        final_sol[a.name] = val.name
                    else:
                        final_sol[a.name] = format_term(val)
            yield final_sol
            count += 1
            if count >= max_solutions: break

    def _rename_variables(self, term):
        self._var_counter += 1
        return rename_variables(term, f"_{self._var_counter}")

    def _resolve(self, name, args, env, context, depth):
        if depth > self.max_depth: return
        if context.cut: return
        if name in BuiltinHandler.BUILTINS or name.startswith('#'):
            yield from self.builtin_handler.handle_builtin(name, args, env, context, depth)
            return
        yield from self._resolve_raw(name, args, env, context, depth)

    def _resolve_raw(self, name, args, env, context, depth):
        first_arg = substitute(args[0], env) if args else None
        if isinstance(first_arg, Atom) and not is_variable(first_arg):
            if name in self.indexed_facts:
                for fact in self.indexed_facts[name].get(first_arg.name, []):
                    m = unify(args, fact, env) 
                    if m: yield m
        
        for fact in self.facts.get(name, []):
            if isinstance(first_arg, Atom) and not is_variable(first_arg) and fact and isinstance(fact[0], Atom) and fact[0] == first_arg:
                continue
            m = unify(args, fact, env)
            if m: yield m

        for rule in self.compiled_rules.get((name, len(args)), []):
            r_name, r_head_args, r_body = rule
            new_head, new_body = self._rename_variables(r_head_args), self._rename_variables(r_body)
            match = unify(args, new_head, env)
            if match:
                base_env = match.copy()
                for res in self._resolve_body(new_body, match, context, depth + 1):
                    trail = {k: res[k] for k in res if k in base_env or not k.name.endswith(f"_{self._var_counter}")}
                    yield trail

    def _resolve_body(self, body, env, context, depth):
        if not body or context.cut: 
            yield env
            return
        goal, rest = body[0], body[1:]
        g_name, g_args = (goal.name, ()) if isinstance(goal, (Atom, Var)) else (goal.functor, goal.args)
        for res in self._resolve(g_name, g_args, env, context, depth):
            if context.cut: return
            yield from self._resolve_body(rest, res, context, depth)