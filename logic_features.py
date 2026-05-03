# logic_features.py
import logging
from logic_types import substitute, deref, unify

logger = logging.getLogger("LogicEngine.Features")

class BuiltinHandler:
    def __init__(self, engine):
        self.engine = engine
        self.constraints = {} 

    def reset_constraints(self):
        self.constraints.clear()

    def handle_builtin(self, name, args, env, context, depth):
        """Dispatches built-in predicates."""
        
        # 1. Control Flow
        if name == 'true':
            yield env
            return
        
        if name == 'fail':
            return

        if name == '!': # Cut
            context.cut = True
            yield env
            return

        if name == 'not': # Negation as Failure
            if len(args) != 1:
                logger.error("not/1 requires 1 argument")
                return
            goal = args[0]
            found = False
            try:
                for _ in self.engine._resolve(goal[0], goal[1], env, context, depth+1):
                    found = True
                    break
            except Exception:
                pass
            
            if not found:
                yield env
            return

        if name == 'call':
            if len(args) != 1:
                return
            goal = args[0]
            yield from self.engine._resolve(goal[0], goal[1], env, context, depth+1)
            return

        # 2. Unification
        if name == '=':
            if len(args) != 2: return
            res = unify(args[0], args[1], env)
            if res: yield res
            return

        if name == '\\=':
            if len(args) != 2: return
            res = unify(args[0], args[1], env)
            if res is None: yield env
            return

        # 3. Arithmetic
        if name == 'is':
            if len(args) != 2: return
            try:
                val = self._eval_arith(args[1], env)
                res = unify(args[0], val, env)
                if res: yield res
            except Exception as e:
                logger.debug(f"Arithmetic error: {e}")
            return

        # 4. Comparison
        if name in ('>', '<', '>=', '=<', '=:=', '=\='):
            if len(args) != 2: return
            try:
                v1 = self._eval_arith(args[0], env)
                v2 = self._eval_arith(args[1], env)
                ops = {
                    '>': lambda a,b: a>b,
                    '<': lambda a,b: a<b,
                    '>=': lambda a,b: a>=b,
                    '=<': lambda a,b: a<=b,
                    '=:=': lambda a,b: a==b,
                    '=\=': lambda a,b: a!=b,
                }
                if ops[name](v1, v2):
                    yield env
            except Exception:
                pass
            return

        # 5. CLP(FD) Mock
        if name == 'ins':
            yield env
            return
        
        if name.startswith('#'):
            yield env
            return

        return

    def _eval_arith(self, term, env):
        term = deref(term, env)
        if isinstance(term, (int, float)):
            return term
        if isinstance(term, str):
            # If it's a variable, it must be bound to a number
            # But deref handles that. If it's still a string, it's unbound.
            raise ValueError(f"Unbound variable in arithmetic: {term}")
        if isinstance(term, tuple):
            op = term[0]
            # Handle binary operations: (Op, Left, Right)
            if len(term) == 3:
                args = [self._eval_arith(a, env) for a in term[1:]]
                if op == '+': return args[0] + args[1]
                if op == '-': return args[0] - args[1]
                if op == '*': return args[0] * args[1]
                if op == '/': return args[0] / args[1]
            # Handle unary minus: ('-', Val)
            if op == '-' and len(term) == 2:
                 return -self._eval_arith(term[1], env)
                 
        raise ValueError(f"Cannot evaluate: {term}")