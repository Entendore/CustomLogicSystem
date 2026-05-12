# tests/test_engine.py
import pytest
import sys
import os
import logging

logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from logic_engine import LogicEngine
from logic_types import Atom, Num, Var, format_term

def _val(result, key):
    """Extract a comparable value from a query result."""
    v = result.get(key)
    if isinstance(v, Atom): return v.name
    if isinstance(v, Num): return v.val
    if isinstance(v, Var): return v.name
    return v

@pytest.fixture
def engine():
    e = LogicEngine()
    yield e
    e.clear()

class TestCoreLogic:
    def test_simple_fact_query(self, engine):
        engine.parse("cat(tom).")
        assert 'cat' in engine.facts, "Fact 'cat' was not parsed"
        engine.optimize()
        results = list(engine.query("cat(X)"))
        assert len(results) == 1
        assert _val(results[0], 'X') == 'tom'

    def test_rule_resolution(self, engine):
        engine.parse("""
        parent(john, mary).
        ancestor(X, Y) :- parent(X, Y).
        """)
        assert 'parent' in engine.facts
        assert len(engine.rules) == 1
        engine.optimize()
        results = list(engine.query("ancestor(john, Y)"))
        assert len(results) == 1
        assert _val(results[0], 'Y') == 'mary'

    def test_recursive_rule(self, engine):
        engine.parse("""
        parent(john, mary).
        parent(mary, susan).
        ancestor(X, Y) :- parent(X, Y).
        ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).
        """)
        engine.optimize()
        results = list(engine.query("ancestor(john, Y)"))
        assert len(results) == 2
        vals = {_val(r, 'Y') for r in results}
        assert vals == {'mary', 'susan'}

    def test_no_solutions(self, engine):
        engine.parse("cat(tom).")
        engine.optimize()
        results = list(engine.query("cat(jerry)"))
        assert len(results) == 0

    def test_incremental_parsing(self, engine):
        """Adding facts incrementally should not erase previous ones."""
        engine.parse("a(1).")
        engine.optimize()
        assert len(list(engine.query("a(1)"))) == 1
        
        engine.parse("a(2).")
        engine.optimize()
        results = list(engine.query("a(X)"))
        assert len(results) == 2
        vals = {_val(r, 'X') for r in results}
        assert vals == {1, 2}

class TestApplicationIntegration:
    def test_cli_style_interaction(self, engine):
        engine.parse("a(1). b(X) :- a(X).")
        engine.optimize()
        assert len(list(engine.query("b(1)"))) == 1
        
    def test_complex_program(self, engine):
        prog = """
        human(socrates).
        mortal(X) :- human(X).
        """
        engine.parse(prog)
        assert 'human' in engine.facts, "Facts were not parsed correctly"
        assert len(engine.rules) > 0, "Rules were not parsed correctly"
        engine.optimize()
        results = list(engine.query("mortal(socrates)"))
        assert len(results) == 1, f"Expected 1 result, got {len(results)}"

    def test_clear_engine(self, engine):
        engine.parse("a(1). b(X) :- a(X).")
        engine.optimize()
        engine.clear()
        assert len(engine.facts) == 0
        assert len(engine.rules) == 0
        results = list(engine.query("a(1)"))
        assert len(results) == 0

class TestArithmetic:
    def test_left_associativity(self, engine):
        engine.parse("test(X) :- X is 1 - 2 - 3.")
        engine.optimize()
        results = list(engine.query("test(R)"))
        assert len(results) == 1
        assert _val(results[0], 'R') == -4

    def test_precedence(self, engine):
        engine.parse("test(X) :- X is 1 + 2 * 3.")
        engine.optimize()
        results = list(engine.query("test(R)"))
        assert len(results) == 1
        assert _val(results[0], 'R') == 7

    def test_multiplication(self, engine):
        engine.parse("test(X) :- X is 3 * 4.")
        engine.optimize()
        results = list(engine.query("test(R)"))
        assert len(results) == 1
        assert _val(results[0], 'R') == 12

    def test_division(self, engine):
        engine.parse("test(X) :- X is 10 / 2.")
        engine.optimize()
        results = list(engine.query("test(R)"))
        assert len(results) == 1
        assert _val(results[0], 'R') == 5.0

    def test_integer_division(self, engine):
        engine.parse("test(X) :- X is 7 // 2.")
        engine.optimize()
        results = list(engine.query("test(R)"))
        assert len(results) == 1
        assert _val(results[0], 'R') == 3

    def test_modulo(self, engine):
        engine.parse("test(X) :- X is 7 mod 3.")
        engine.optimize()
        results = list(engine.query("test(R)"))
        assert len(results) == 1
        assert _val(results[0], 'R') == 1

    def test_exponentiation(self, engine):
        engine.parse("test(X) :- X is 2 ** 3.")
        engine.optimize()
        results = list(engine.query("test(R)"))
        assert len(results) == 1
        assert _val(results[0], 'R') == 8

class TestControlFlow:
    def test_disjunction(self, engine):
        engine.parse("val(1). val(2). result(X) :- val(X), (X = 1; X = 2).")
        engine.optimize()
        results = list(engine.query("result(R)"))
        assert len(results) == 2
        vals = {_val(r, 'R') for r in results}
        assert vals == {1, 2}

    def test_if_then_else(self, engine):
        prog = """
        classify(X, Y) :- 
            (X = 1 -> Y = a ; Y = b).
        """
        engine.parse(prog)
        engine.optimize()
        
        r1 = list(engine.query("classify(1, R)"))
        assert len(r1) == 1 and _val(r1[0], 'R') == 'a'
        
        r2 = list(engine.query("classify(2, R)"))
        assert len(r2) == 1 and _val(r2[0], 'R') == 'b'

    def test_cut(self, engine):
        engine.parse("""
        val(1). val(2). val(3).
        first(X) :- val(X), !.
        """)
        engine.optimize()
        results = list(engine.query("first(R)"))
        assert len(results) == 1
        assert _val(results[0], 'R') == 1

    def test_negation_as_failure(self, engine):
        engine.parse("""
        cat(tom).
        dog(X) :- not(cat(X)).
        """)
        engine.optimize()
        # tom is a cat, so dog(tom) should fail
        r1 = list(engine.query("dog(tom)"))
        assert len(r1) == 0
        # fido is not a cat, so dog(fido) should succeed
        r2 = list(engine.query("dog(fido)"))
        assert len(r2) == 1

class TestUnification:
    def test_unify_variable(self, engine):
        engine.parse("same(X, X).")
        engine.optimize()
        results = list(engine.query("same(a, R)"))
        assert len(results) == 1
        assert _val(results[0], 'R') == 'a'

    def test_unify_compound(self, engine):
        engine.parse("pair(f(a, b), c).")
        engine.optimize()
        results = list(engine.query("pair(f(a, X), Y)"))
        assert len(results) == 1
        assert _val(results[0], 'X') == 'b'
        assert _val(results[0], 'Y') == 'c'

    def test_not_unifiable(self, engine):
        engine.parse("pair(a, b).")
        engine.optimize()
        results = list(engine.query("pair(a, a)"))
        assert len(results) == 0

class TestComparison:
    def test_greater_than(self, engine):
        engine.parse("bigger(X, Y) :- X > Y.")
        engine.optimize()
        assert len(list(engine.query("bigger(5, 3)"))) == 1
        assert len(list(engine.query("bigger(3, 5)"))) == 0

    def test_less_than(self, engine):
        engine.parse("smaller(X, Y) :- X < Y.")
        engine.optimize()
        assert len(list(engine.query("smaller(3, 5)"))) == 1
        assert len(list(engine.query("smaller(5, 3)"))) == 0

    def test_arithmetic_equal(self, engine):
        engine.parse("eq(X, Y) :- X =:= Y.")
        engine.optimize()
        assert len(list(engine.query("eq(3, 3)"))) == 1
        assert len(list(engine.query("eq(3, 4)"))) == 0

class TestLists:
    def test_append(self, engine):
        engine.parse("""
        append([], L, L).
        append([H|T], L, [H|R]) :- append(T, L, R).
        """)
        engine.optimize()
        
        # Test appending to empty list
        results = list(engine.query("append([], [1,2], R)"))
        assert len(results) == 1
        
        # Test appending two lists
        results = list(engine.query("append([1,2], [3,4], R)"))
        assert len(results) == 1
        
        # Test finding prefix
        results = list(engine.query("append(X, [3], [1,2,3])"))
        assert len(results) == 1

class TestDCG:
    def test_simple_dcg(self, engine):
        engine.parse("""
        word --> [hello].
        """)
        engine.optimize()
        # DCG expands to word(S0, S) :- S0 = [hello|S].
        results = list(engine.query("word([hello|T], T)"))
        assert len(results) == 1

    def test_dcg_sequence(self, engine):
        engine.parse("""
        sentence --> noun, verb.
        noun --> [the].
        verb --> [runs].
        """)
        engine.optimize()
        results = list(engine.query("sentence([the, runs], [])"))
        assert len(results) == 1

class TestEdgeCases:
    def test_singleton_variable_in_rule(self, engine):
        """Rules with singleton variables should still work."""
        engine.parse("dummy(X) :- true.")
        engine.optimize()
        results = list(engine.query("dummy(a)"))
        assert len(results) == 1

    def test_anonymous_variable(self, engine):
        """Anonymous variables (_) should not appear in results."""
        engine.parse("pair(_, Y).")
        engine.optimize()
        results = list(engine.query("pair(a, R)"))
        assert len(results) == 1
        # Only R should appear, not _
        assert 'R' in results[0]
        assert '_' not in results[0]

    def test_max_solutions_limit(self, engine):
        """Query should respect max_solutions parameter."""
        engine.parse("num(1). num(2). num(3). num(4). num(5).")
        engine.optimize()
        results = list(engine.query("num(X)", max_solutions=3))
        assert len(results) == 3

    def test_multiple_rules_same_predicate(self, engine):
        engine.parse("""
        animal(cat).
        animal(dog).
        animal(fish).
        """)
        engine.optimize()
        results = list(engine.query("animal(X)"))
        assert len(results) == 3
        vals = {_val(r, 'X') for r in results}
        assert vals == {'cat', 'dog', 'fish'}