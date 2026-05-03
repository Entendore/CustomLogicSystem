# tests/test_parser.py
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from logic_parser import parse_predicate, parse_program
from logic_types import parse_term

class TestTermParsing:
    def test_atom(self):
        assert parse_term('hello') == 'hello'
    
    def test_variable(self):
        assert parse_term('Var') == 'Var'
        assert parse_term('_Var') == '_Var'

    def test_integer(self):
        assert parse_term('123') == 123
    
    def test_float(self):
        assert parse_term('12.5') == 12.5

    def test_compound(self):
        result = parse_term('func(a, B)')
        assert isinstance(result, tuple)
        assert result[0] == 'func'
        assert result[1] == ('a', 'B')

    def test_list_empty(self):
        assert parse_term('[]') == ('nil',)

    def test_list_flat(self):
        # [1, 2] -> cons(1, cons(2, nil))
        result = parse_term('[1, 2]')
        assert result[0] == 'cons'
        assert result[1] == 1
        assert result[2][0] == 'cons'
        assert result[2][2] == ('nil',)

class TestPredicateParsing:
    def test_simple_predicate(self):
        name, args = parse_predicate('my_pred(a, b)')
        assert name == 'my_pred'
        assert args == ['a', 'b']

    def test_infix_is(self):
        name, args = parse_predicate('X is 5')
        assert name == 'is'
        assert args[0] == 'X'
        assert args[1] == 5

    def test_infix_unification(self):
        name, args = parse_predicate('A = B')
        assert name == '='
        assert args == ['A', 'B']

class TestProgramParsing:
    def test_parse_fact(self):
        facts, rules = parse_program("cat(tom).")
        assert 'cat' in facts
        assert len(rules) == 0
        assert facts['cat'][0] == ('tom',)

    def test_parse_rule(self):
        facts, rules = parse_program("a :- b.")
        assert len(rules) == 1
        r_name, r_args, r_body = rules[0]
        assert r_name == 'a'
        assert r_body[0][0] == 'b'

    def test_parse_dcg(self):
        facts, rules = parse_program("word --> [hello].")
        assert len(rules) == 1
        r_name, r_args, r_body = rules[0]
        
        # DCG expands word --> [hello]. into:
        # word(S0, S) :- S0 = [hello|S].
        assert r_name == 'word'
        assert r_args == ['S0', 'S']
        
        # Check body structure: =(S0, cons(hello, S))
        goal = r_body[0]
        assert goal[0] == '='
        unif_args = goal[1]
        assert unif_args[0] == 'S0' # The input list
        # unif_args[1] should be cons structure
        assert unif_args[1][0] == 'cons' 