# tests/test_engine.py
import pytest
import sys
import os

# Add parent directory to path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from logic_engine import LogicEngine

@pytest.fixture
def engine():
    """Provides a fresh LogicEngine instance for each test."""
    e = LogicEngine()
    yield e
    e.clear()

class TestCoreLogic:
    def test_simple_fact_query(self, engine):
        """Test simple fact parsing and query."""
        engine.parse("cat(tom).")
        engine.optimize()
        results = list(engine.query("cat(X)"))
        assert len(results) == 1
        assert results[0].get('X') == 'tom'

    def test_rule_resolution(self, engine):
        """Test rule parsing and resolution."""
        engine.parse("""
        parent(john, mary).
        ancestor(X, Y) :- parent(X, Y).
        """)
        engine.optimize()
        results = list(engine.query("ancestor(john, Y)"))
        assert len(results) == 1
        assert results[0].get('Y') == 'mary'

    def test_conjunction(self, engine):
        """Test queries with multiple goals (AND)."""
        engine.parse("""
        a(1).
        b(1).
        c(X) :- a(X), b(X).
        """)
        engine.optimize()
        results = list(engine.query("c(1)"))
        assert len(results) == 1

class TestArithmetic:
    def test_is_evaluation(self, engine):
        engine.parse("val(X) :- X is 2 + 3.")
        engine.optimize()
        res = list(engine.query("val(Y)"))
        assert len(res) == 1
        assert res[0].get('Y') == 5

    def test_comparison_success(self, engine):
        engine.parse("ok :- 5 > 2.")
        engine.optimize()
        assert len(list(engine.query("ok"))) == 1

    def test_comparison_failure(self, engine):
        engine.parse("ok :- 1 > 5.")
        engine.optimize()
        assert len(list(engine.query("ok"))) == 0

    def test_unification_with_arith(self, engine):
        engine.parse("eq(X) :- X is 10, X =:= 10.")
        engine.optimize()
        assert len(list(engine.query("eq(10)"))) == 1

class TestLists:
    def test_list_unification(self, engine):
        engine.parse("data([1, 2, 3]).")
        engine.optimize()
        # Query matching head/tail
        res = list(engine.query("data([H|T])"))
        assert res[0].get('H') == 1
        # parse_term logic returns nested cons tuples, format_term handles display
        # logic_types parses [1,2,3] as ('cons', 1, ('cons', 2, ...))
        tail = res[0].get('T')
        # Verify tail structure roughly
        assert tail[0] == 'cons' 

    def test_recursive_list_sum(self, engine):
        # Sum a list of numbers
        code = """
        sum([], 0).
        sum([H|T], Total) :- sum(T, Rest), Total is H + Rest.
        """
        engine.parse(code)
        engine.optimize()
        res = list(engine.query("sum([10, 20, 30], S)"))
        assert len(res) == 1
        assert res[0].get('S') == 60

class TestControlFlow:
    def test_cut(self, engine):
        """Test that cut prevents backtracking."""
        code = """
        test(X) :- X = 1, !.
        test(X) :- X = 2.
        """
        engine.parse(code)
        engine.optimize()
        res = list(engine.query("test(Y)"))
        assert len(res) == 1
        assert res[0].get('Y') == 1 # Should not find 2

    def test_fail(self, engine):
        engine.parse("a(1). a(2) :- fail.")
        engine.optimize()
        res = list(engine.query("a(X)"))
        assert len(res) == 1
        assert res[0].get('X') == 1

    def test_negation_as_failure(self, engine):
        code = """
        cat(tom).
        dog(X) :- not(cat(X)).
        """
        engine.parse(code)
        engine.optimize()
        # jerry is not a cat
        assert len(list(engine.query("dog(jerry)"))) == 1
        # tom is a cat
        assert len(list(engine.query("dog(tom)"))) == 0

class TestRecursion:
    def test_fibonacci(self, engine):
        code = """
        fib(0, 0).
        fib(1, 1).
        fib(N, R) :- N > 1, N1 is N - 1, N2 is N - 2, fib(N1, R1), fib(N2, R2), R is R1 + R2.
        """
        engine.parse(code)
        engine.optimize()
        res = list(engine.query("fib(10, F)"))
        assert len(res) == 1
        assert res[0].get('F') == 55

class TestDCG:
    def test_dcg_parsing(self, engine):
        """Test that DCG rules are expanded correctly."""
        code = """
        sentence --> noun_phrase, verb_phrase.
        noun_phrase --> det, noun.
        verb_phrase --> verb.
        det --> [the].
        noun --> [cat].
        verb --> [sleeps].
        """
        engine.parse(code)
        engine.optimize()
        solutions = list(engine.query("sentence([the, cat, sleeps], [])"))
        assert len(solutions) == 1

    def test_dcg_terminal_unification(self, engine):
        engine.parse("word --> [hello].")
        engine.optimize()
        assert len(list(engine.query("word([hello], [])"))) == 1
        assert len(list(engine.query("word([world], [])"))) == 0

class TestTabling:
    def test_tabling_prevents_infinite_loop(self, engine):
        """Test that tabling prevents infinite loops in cyclic graphs."""
        code = """
        path(a, b).
        path(b, a).
        reachable(X, Y) :- path(X, Y).
        reachable(X, Y) :- path(X, Z), reachable(Z, Y).
        """
        engine.parse(code)
        engine.table('reachable/2') # Enable tabling
        engine.optimize()
        
        try:
            results = list(engine.query("reachable(a, X)", max_solutions=10))
            found = {r.get('X') for r in results}
            assert 'b' in found
            assert 'a' in found # a -> b -> a
        except RecursionError:
            pytest.fail("Tabling failed to prevent recursion error.")