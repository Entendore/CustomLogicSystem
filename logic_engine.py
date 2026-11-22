# logic_engine.py
import logging
from collections import defaultdict
from logic_types import (substitute, unify, is_variable, deref, ResolveContext, 
                         rename_variables, Atom, Var, Num, Compound, format_term)
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
        # FIX: Merge new facts/rules into existing KB instead of clearing,
        # enabling incremental additions from CLI
        new_facts, new_rules = parse_program(program, filename)
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
                if is_variable(a) and not a.name.startswith('_'):
                    val = deref(a, sol)
                    final_sol[a.name] = val
            yield final_sol
            count += 1
            if count >= max_solutions: break

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
            
            # FIX: Generate ONE suffix and ONE rename_table per rule application,
            # and apply it to every term inside the head tuple and body list!
            self._var_counter += 1
            suffix = f"_{self._var_counter}"
            rename_table = {}  # Shared table preserves variable identity within rule
            new_head = tuple(rename_variables(a, suffix, rename_table) for a in r_head_args)
            new_body = [rename_variables(g, suffix, rename_table) for g in r_body]
            
            match = unify(args, new_head, env)
            if match:
                base_env = match.copy()
                for res in self._resolve_body(new_body, match, context, depth + 1):
                    # FIX: Only yield bindings for variables that existed in the
                    # calling context (base_env) or are original user variables
                    # (not ending with the renaming suffix).
                    trail = {}
                    for k, v in res.items():
                        if k in base_env or not k.name.endswith(suffix):
                            trail[k] = v
                    yield trail
                    if context.cut: break
                if context.cut: break

    def _resolve_body(self, body, env, context, depth):
        if not body:
            yield env
            return
            
        goal, rest = body[0], body[1:]
        
        # Handle Variable calls dynamically
        if isinstance(goal, Var):
            goal = deref(goal, env)
            if isinstance(goal, Var): return
            # Deref'd to a compound/atom - resolve that instead
            
        if isinstance(goal, Atom):
            g_name, g_args = goal.name, ()
        elif isinstance(goal, Compound):
            g_name, g_args = goal.functor, goal.args
        else:
            return
            
        for res in self._resolve(g_name, g_args, env, context, depth):
            if context.cut:
                saved_cut = context.cut
                context.cut = False
                yield from self._resolve_body(rest, res, context, depth)
                context.cut = saved_cut
                return
            yield from self._resolve_body(rest, res, context, depth)