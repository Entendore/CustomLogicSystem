# logic_engine.py
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from logic_types import substitute, unify, is_variable, deref, ResolveContext
from logic_features import BuiltinHandler
from logic_parser import parse_program

logger = logging.getLogger("LogicEngine")

class LogicEngine:
    def __init__(self):
        self.facts = defaultdict(list)
        self.rules = []
        self.loaded_files = set()
        
        self.indexed_facts = defaultdict(lambda: defaultdict(list))
        self.compiled_rules = defaultdict(list)
        
        self.query_count = 0
        self.max_depth = 1000
        self.parallel_enabled = False
        self.thread_pool = None
        self.trace_enabled = False
        
        self.tabled_predicates = set()
        self.memo_table = defaultdict(list)
        self.foreign_functions = {}
        
        self.builtin_handler = BuiltinHandler(self)

    # --- Management ---

    def parse(self, program, filename="input"):
        """Parses a program string and updates the knowledge base."""
        new_facts, new_rules = parse_program(program, filename)
        
        self.facts.clear()
        self.rules.clear()
        
        # Inject parsed data
        for name, fact_list in new_facts.items():
            self.facts[name].extend(fact_list)
        self.rules.extend(new_rules)

    def optimize(self):
        logger.info("Optimizing knowledge base...")
        self.indexed_facts.clear()
        self.compiled_rules.clear()
        
        for pred, facts in self.facts.items():
            for f in facts:
                if f and isinstance(f[0], str) and not is_variable(f[0]):
                    self.indexed_facts[pred][f[0]].append(f)
        
        for r in self.rules:
            key = (r[0], len(r[1]))
            self.compiled_rules[key].append(r)

    def clear(self):
        self.facts.clear()
        self.rules.clear()
        self.builtin_handler.reset_constraints()
        self.memo_table.clear()
        logger.info("Engine cleared.")

    def table(self, pred_sig):
        self.tabled_predicates.add(pred_sig)
        logger.info(f"Tabled: {pred_sig}")

    # --- Query Interface ---

    def query(self, query_str, max_solutions=100):
        self.query_count += 1
        self.builtin_handler.reset_constraints()
        
        # Use parser for query string as well
        from logic_parser import parse_predicate
        q_name, q_args = parse_predicate(query_str)
        
        context = ResolveContext()
        
        if self.parallel_enabled and not self.thread_pool:
            self.thread_pool = ThreadPoolExecutor(max_workers=4)
            
        try:
            count = 0
            for sol in self._resolve(q_name, q_args, {}, context, 0):
                yield sol
                count += 1
                if count >= max_solutions: break
        finally:
            if self.thread_pool:
                self.thread_pool.shutdown(wait=False)
                self.thread_pool = None

    # --- Resolution (Internal) ---

    def _resolve(self, name, args, env, context, depth):
        if depth > self.max_depth:
            logger.error("Max recursion depth exceeded.")
            return
        if context.cut: return

        pred_key = (name, len(args))
        
        if self.trace_enabled:
            logger.debug(f"{' '*depth}CALL: {name}({', '.join(map(str, args))})")

        # 1. Foreign Functions
        if pred_key in self.foreign_functions:
            func = self.foreign_functions[pred_key]
            try:
                resolved_args = [substitute(a, env) for a in args]
                for result_dict in func(*resolved_args):
                    new_env = env.copy()
                    new_env.update(result_dict)
                    yield new_env
            except Exception as e:
                logger.error(f"FFI Error {name}: {e}")
            return

        # 2. Built-ins
        builtin_gen = self.builtin_handler.handle_builtin(name, args, env, context, depth)
        if builtin_gen:
            yield from builtin_gen
            return

        # 3. Tabling
        sig = f"{name}/{len(args)}"
        if sig in self.tabled_predicates:
            key = (name, tuple(deref(a, env) for a in args))
            
            if key in self.memo_table:
                for s in self.memo_table[key]: 
                    yield s.copy()
                return
            
            self.memo_table[key] = []
            
            results = []
            for s in self._resolve_raw(name, args, env, context, depth):
                results.append(s.copy())
                yield s
            
            self.memo_table[key] = results
            return

        # 4. Standard
        yield from self._resolve_raw(name, args, env, context, depth)

    def _resolve_raw(self, name, args, env, context, depth):
        first_arg = substitute(args[0], env) if args else None
        
        if isinstance(first_arg, str) and not is_variable(first_arg):
            if name in self.indexed_facts:
                for fact in self.indexed_facts[name].get(first_arg, []):
                    m = unify(tuple(args), fact, env) 
                    if m: yield m
                return 

        alternatives = []
        
        for fact in self.facts.get(name, []):
            alternatives.append(('fact', fact))
            
        for rule in self.compiled_rules.get((name, len(args)), []):
            alternatives.append(('rule', rule))
            
        if self.parallel_enabled and len(alternatives) > 1:
            futures = []
            for alt in alternatives:
                fut = self.thread_pool.submit(self._resolve_alt, alt, args, env, context, depth)
                futures.append(fut)
            
            for fut in as_completed(futures):
                for res in fut.result():
                    yield res
        else:
            for alt in alternatives:
                if context.cut: return
                for res in self._resolve_alt(alt, args, env, context, depth):
                    yield res

    def _resolve_alt(self, alt_type, data, args, env, context, depth):
        if alt_type == 'fact':
            match = unify(tuple(args), data, env)
            if match: yield match
            
        elif alt_type == 'rule':
            r_name, r_head, r_body = data
            match = unify(tuple(args), r_head, env)
            if match:
                yield from self._resolve_body(r_body, match, context, depth + 1)

    def _resolve_body(self, body, env, context, depth):
        if not body or context.cut: 
            yield env
            return
        
        goal = body[0]
        rest = body[1:]
        g_name = goal[0]
        g_args = goal[1]
        
        for res in self._resolve(g_name, g_args, env, context, depth):
            if context.cut: return
            yield from self._resolve_body(rest, res, context, depth)