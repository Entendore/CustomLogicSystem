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
        # FIX: Flattened structure check
        result = parse_term('func(a, B)')
        assert isinstance(result, tuple)
        assert result[0] == 'func'
        assert result[1] == 'a'
        assert result[2] == 'B'

    def test_list_empty(self):
        assert parse_term('[]') == ('nil',)

    def test_list_flat(self):
        result = parse_term('[1, 2]')
        assert result[0] == 'cons'
        assert result[1] == 1
        assert result[2][0] == 'cons'
        assert result[2][2] == ('nil',)

    def test_list_head_tail(self):
        result = parse_term('[a, b | T]')
        assert result[0] == 'cons'
        assert result[1] == 'a'
        rest = result[2]
        assert rest[0] == 'cons'
        assert rest[1] == 'b'
        assert rest[2] == 'T'

    def test_unary_minus(self):
        assert parse_term('-5') == -5
        assert parse_term('-X') == ('-', 'X')

    def test_left_associativity_math(self):
        result = parse_term('1 - 2 - 3')
        assert result[0] == '-'
        assert result[1][0] == '-'
        assert result[1][1] == 1
        assert result[1][2] == 2
        assert result[2] == 3

    def test_mixed_precedence(self):
        result = parse_term('1 + 2 * 3')
        assert result[0] == '+'
        assert result[1] == 1
        assert result[2][0] == '*'
        assert result[2][1] == 2
        assert result[2][2] == 3

class TestPredicateParsing:
    def test_simple_predicate(self):
        name, args = parse_predicate('my_pred(a, b)')
        assert name == 'my_pred'
        # FIX: args are now flattened ['a', 'b']
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
        # FIX: Fact is stored as tuple of args: ('tom',)
        assert facts['cat'][0] == ('tom',)

    def test_parse_rule(self):
        facts, rules = parse_program("a :- b.")
        assert len(rules) == 1
        r_name, r_args, r_body = rules[0]
        assert r_name == 'a'
        assert r_body[0][0] == 'b'
    
    def test_parse_conjunction_body(self):
        facts, rules = parse_program("a :- b, c, d.")
        _, _, body = rules[0]
        assert len(body) == 3
        assert body[0][0] == 'b'
        assert body[1][0] == 'c'
        assert body[2][0] == 'd'

    def test_parse_disjunction_body(self):
        # a :- b ; c.
        facts, rules = parse_program("a :- b ; c.")
        _, _, body = rules[0]
        assert len(body) == 1
        goal = body[0]
        assert goal[0] == ';'
        # FIX: goal structure is (Name, ArgsList)
        # goal[1] is the list of arguments ['b', 'c']
        assert goal[1][0] == 'b' # Left side
        assert goal[1][1] == 'c' # Right side

    def test_parse_dcg(self):
        facts, rules = parse_program("word --> [hello].")
        assert len(rules) == 1
        r_name, r_args, r_body = rules[0]
        
        assert r_name == 'word'
        assert r_args == ['S0', 'S']
        
        goal = r_body[0]
        assert goal[0] == '='
        unif_args = goal[1]
        assert unif_args[0] == 'S0' 
        assert unif_args[1][0] == 'cons' 