# tests/test_engine.py
import pytest
import sys
import os
import logging

logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from logic_engine import LogicEngine

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
        assert results[0].get('X') == 'tom'

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
        assert results[0].get('Y') == 'mary'

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

class TestArithmetic:
    def test_left_associativity(self, engine):
        # 1 - 2 - 3 should be (1 - 2) - 3 = -4
        engine.parse("test(X) :- X is 1 - 2 - 3.")
        engine.optimize()
        results = list(engine.query("test(R)"))
        assert len(results) == 1
        assert results[0]['R'] == -4

    def test_precedence(self, engine):
        # 1 + 2 * 3 should be 1 + (2 * 3) = 7
        engine.parse("test(X) :- X is 1 + 2 * 3.")
        engine.optimize()
        results = list(engine.query("test(R)"))
        assert len(results) == 1
        assert results[0]['R'] == 7

class TestControlFlow:
    def test_disjunction(self, engine):
        engine.parse("val(1). val(2). result(X) :- val(X), (X = 1; X = 2).")
        engine.optimize()
        results = list(engine.query("result(R)"))
        assert len(results) == 2
        vals = {r['R'] for r in results}
        assert vals == {1, 2}

    def test_if_then_else(self, engine):
        # if X=1 then Y=a else Y=b
        prog = """
        classify(X, Y) :- 
            (X = 1 -> Y = a ; Y = b).
        """
        engine.parse(prog)
        engine.optimize()
        
        r1 = list(engine.query("classify(1, R)"))
        assert len(r1) == 1 and r1[0]['R'] == 'a'
        
        r2 = list(engine.query("classify(2, R)"))
        assert len(r2) == 1 and r2[0]['R'] == 'b'