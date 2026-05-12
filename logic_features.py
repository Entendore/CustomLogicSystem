# logic_features.py
import logging
import operator
from logic_types import substitute, deref, unify, is_variable, Num, Atom, Var, Compound

logger = logging.getLogger("LogicEngine.Features")

class BuiltinHandler:
    BUILTINS = {
        'true', 'fail', '!', ';', ',', '->', 'not', 'call', 
        '=', '\\=', 'is', '>', '<', '>=', '=<', '=:=', '=\=', 'ins'
    }
    
    def __init__(self, engine):
        self.engine = engine
        self.constraints = {} 

    def reset_constraints(self):
        self.constraints.clear()

    def handle_builtin(self, name, args, env, context, depth):
        if name == 'true': yield env; return
        if name == 'fail': return
        if name == '!': context.cut = True; yield env; return
        
        if name == ',':
            if len(args) == 2:
                for env1 in self.engine._resolve_body((args[0],), env, context, depth+1):
                    if context.cut: return
                    yield from self.engine._resolve_body((args[1],), env1, context, depth+1)
            return

        if name == ';':
            if len(args) == 2:
                left, right = args[0], args[1]
                if isinstance(left, Compound) and left.functor == '->':
                    cond, then, else_ = left.args[0], left.args[1], right
                    context.push_cut_scope()
                    found = False
                    for env1 in self.engine._resolve_body((cond,), env, context, depth+1):
                        found = True
                        yield from self.engine._resolve_body((then,), env1, context, depth+1)
                        break
                    cut_occurred = context.pop_cut_scope()
                    if not found and not cut_occurred:
                        yield from self.engine._resolve_body((else_,), env, context, depth+1)
                else:
                    yield from self.engine._resolve_body((left,), env, context, depth+1)
                    if context.cut: return
                    yield from self.engine._resolve_body((right,), env, context, depth+1)
            return

        if name == '->':
            if len(args) == 2:
                context.push_cut_scope()
                for env1 in self.engine._resolve_body((args[0],), env, context, depth+1):
                    yield from self.engine._resolve_body((args[1],), env1, context, depth+1)
                    break
                context.pop_cut_scope()
            return

        if name == 'not': 
            found = any(True for _ in self.engine._resolve_body((args[0],), env, type(context)(), depth+1))
            if not found: yield env
            return

        if name == 'call':
            yield from self.engine._resolve_body((args[0],), env, context, depth+1)
            return

        if name == '=':
            res = unify(args[0], args[1], env)
            if res: yield res
            return

        if name == '\\=':
            if unify(args[0], args[1], env) is None: yield env
            return

        if name == 'is':
            try:
                val = self._eval_arith(args[1], env)
                res = unify(args[0], Num(val), env)
                if res: yield res
            except Exception: pass
            return

        if name in ('>', '<', '>=', '=<', '=:=', '=\='):
            try:
                v1, v2 = self._eval_arith(args[0], env), self._eval_arith(args[1], env)
                ops = {
                    '>': operator.gt, '<': operator.lt, '>=': operator.ge, 
                    '=<': operator.le, '=:=': operator.eq, '=\=': operator.ne
                }
                if ops[name](v1, v2): yield env
            except Exception: pass
            return
        
        if name == 'ins': yield env; return
        if name.startswith('#'): yield env; return

    def _eval_arith(self, term, env):
        term = deref(term, env)
        if isinstance(term, Num): return term.val
        if isinstance(term, (Var, Atom)): raise ValueError("Unbound variable")
        if isinstance(term, Compound):
            op = term.functor
            if op == '-' and len(term.args) == 1: return -self._eval_arith(term.args[0], env)
            if len(term.args) == 2:
                v1, v2 = self._eval_arith(term.args[0], env), self._eval_arith(term.args[1], env)
                if op == '+': return v1 + v2
                if op == '-': return v1 - v2
                if op == '*': return v1 * v2
                if op == '/': return v1 / v2
                if op == '//': return int(v1 // v2)
                if op == 'mod': return v1 % v2
                if op == '**': return v1 ** v2
        raise ValueError("Cannot evaluate")