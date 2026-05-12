# tests/test_parser.py
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from logic_parser import parse_predicate, parse_program
from logic_types import parse_term, Atom, Var, Num, Compound, Cons, Nil

class TestTermParsing:
    def test_atom(self):
        result = parse_term('hello')
        assert isinstance(result, Atom)
        assert result.name == 'hello'
    
    def test_variable(self):
        result = parse_term('Var')
        assert isinstance(result, Var)
        assert result.name == 'Var'

    def test_anonymous_variable(self):
        result = parse_term('_Var')
        assert isinstance(result, Var)
        assert result.name == '_Var'

    def test_integer(self):
        result = parse_term('123')
        assert isinstance(result, Num)
        assert result.val == 123
    
    def test_float(self):
        result = parse_term('12.5')
        assert isinstance(result, Num)
        assert result.val == 12.5

    def test_compound(self):
        result = parse_term('func(a, B)')
        assert isinstance(result, Compound)
        assert result.functor == 'func'
        assert isinstance(result.args[0], Atom) and result.args[0].name == 'a'
        assert isinstance(result.args[1], Var) and result.args[1].name == 'B'

    def test_list_empty(self):
        result = parse_term('[]')
        assert isinstance(result, Nil)

    def test_list_flat(self):
        result = parse_term('[1, 2]')
        assert isinstance(result, Cons)
        assert isinstance(result.head, Num) and result.head.val == 1
        assert isinstance(result.tail, Cons)
        assert isinstance(result.tail.tail, Nil)

    def test_list_head_tail(self):
        result = parse_term('[a, b | T]')
        assert isinstance(result, Cons)
        assert isinstance(result.head, Atom) and result.head.name == 'a'
        rest = result.tail
        assert isinstance(rest, Cons)
        assert isinstance(rest.head, Atom) and rest.head.name == 'b'
        assert isinstance(rest.tail, Var) and rest.tail.name == 'T'

    def test_unary_minus_number(self):
        result = parse_term('-5')
        assert isinstance(result, Num)
        assert result.val == -5

    def test_unary_minus_variable(self):
        result = parse_term('-X')
        assert isinstance(result, Compound)
        assert result.functor == '-'
        assert isinstance(result.args[0], Var) and result.args[0].name == 'X'

    def test_left_associativity_math(self):
        result = parse_term('1 - 2 - 3')
        assert isinstance(result, Compound)
        assert result.functor == '-'
        assert isinstance(result.args[0], Compound)
        assert result.args[0].functor == '-'
        assert result.args[0].args[0] == Num(1)
        assert result.args[0].args[1] == Num(2)
        assert result.args[1] == Num(3)

    def test_mixed_precedence(self):
        result = parse_term('1 + 2 * 3')
        assert isinstance(result, Compound)
        assert result.functor == '+'
        assert result.args[0] == Num(1)
        assert isinstance(result.args[1], Compound)
        assert result.args[1].functor == '*'
        assert result.args[1].args[0] == Num(2)
        assert result.args[1].args[1] == Num(3)

    def test_variable_sharing_within_clause(self):
        """Same variable name in a clause should resolve to the same Var object."""
        var_table = {}
        t1 = parse_term('X', var_table)
        t2 = parse_term('X', var_table)
        assert t1 is t2, "Same variable name should return same Var object"

    def test_different_variables_in_clause(self):
        """Different variable names should be different Var objects."""
        var_table = {}
        t1 = parse_term('X', var_table)
        t2 = parse_term('Y', var_table)
        assert t1 is not t2

class TestPredicateParsing:
    def test_simple_predicate(self):
        name, args = parse_predicate('my_pred(a, b)')
        assert name == 'my_pred'
        assert len(args) == 2
        assert isinstance(args[0], Atom) and args[0].name == 'a'
        assert isinstance(args[1], Atom) and args[1].name == 'b'

    def test_infix_is(self):
        name, args = parse_predicate('X is 5')
        assert name == 'is'
        assert isinstance(args[0], Var) and args[0].name == 'X'
        assert isinstance(args[1], Num) and args[1].val == 5

    def test_infix_unification(self):
        name, args = parse_predicate('A = B')
        assert name == '='
        assert isinstance(args[0], Var) and args[0].name == 'A'
        assert isinstance(args[1], Var) and args[1].name == 'B'

class TestProgramParsing:
    def test_parse_fact(self):
        facts, rules = parse_program("cat(tom).")
        assert 'cat' in facts
        assert len(rules) == 0
        assert len(facts['cat']) == 1
        assert isinstance(facts['cat'][0][0], Atom) and facts['cat'][0][0].name == 'tom'

    def test_parse_rule(self):
        facts, rules = parse_program("a :- b.")
        assert len(rules) == 1
        r_name, r_args, r_body = rules[0]
        assert r_name == 'a'
        assert isinstance(r_body[0], Atom) and r_body[0].name == 'b'
    
    def test_parse_conjunction_body(self):
        facts, rules = parse_program("a :- b, c, d.")
        _, _, body = rules[0]
        assert len(body) == 3
        assert isinstance(body[0], Atom) and body[0].name == 'b'
        assert isinstance(body[1], Atom) and body[1].name == 'c'
        assert isinstance(body[2], Atom) and body[2].name == 'd'

    def test_parse_disjunction_body(self):
        facts, rules = parse_program("a :- b ; c.")
        _, _, body = rules[0]
        assert len(body) == 1
        goal = body[0]
        assert isinstance(goal, Compound)
        assert goal.functor == ';'
        assert isinstance(goal.args[0], Atom) and goal.args[0].name == 'b'
        assert isinstance(goal.args[1], Atom) and goal.args[1].name == 'c'

    def test_parse_dcg(self):
        facts, rules = parse_program("word --> [hello].")
        assert len(rules) == 1
        r_name, r_args, r_body = rules[0]
        
        assert r_name == 'word'
        assert len(r_args) == 4  # original args + S0 + Sn
        
        goal = r_body[0]
        assert isinstance(goal, Compound)
        assert goal.functor == '='

    def test_rule_variable_sharing(self):
        """Variables with the same name in head and body should be the same object."""
        facts, rules = parse_program("a(X) :- b(X).")
        r_name, r_args, r_body = rules[0]
        head_var = r_args[0]
        body_var = r_body[0].args[0]
        assert head_var is body_var, "Same-named variables in head and body must be identical"

    def test_multiple_facts_same_predicate(self):
        facts, rules = parse_program("val(1). val(2). val(3).")
        assert 'val' in facts
        assert len(facts['val']) == 3