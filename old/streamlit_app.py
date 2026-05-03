# streamlit_app.py
import streamlit as st
import pandas as pd
import io
import sys
import time
import re
from contextlib import redirect_stdout
import traceback

# Import the logic engine
from logic_engine import LogicEngine, format_term, substitute

def streamlit_app():
    st.set_page_config(
        page_title="Advanced Logic Programming System",
        page_icon="🧠",
        layout="wide"
    )
    
    st.title("🧠 Advanced Logic Programming System")
    st.markdown("A powerful logic programming system with tabling, FFI, debugging, DCGs, constraints, and parallel execution.")
    
    # Initialize session state
    if 'engine' not in st.session_state:
        st.session_state.engine = LogicEngine()
        st.session_state.query_history = []
        st.session_state.knowledge_base = ""
        
        # Load default examples
        preload_examples()
    
    # Sidebar for controls
    with st.sidebar:
        st.header("Controls")
        
        # Knowledge base management
        st.subheader("Knowledge Base")
        if st.button("Clear Knowledge Base"):
            st.session_state.engine.clear()
            st.session_state.knowledge_base = ""
            st.success("Knowledge base cleared!")
            st.experimental_rerun()
        
        # File operations
        st.subheader("File Operations")
        uploaded_file = st.file_uploader("Load Logic File", type=['pl', 'prolog', 'txt'])
        if uploaded_file is not None:
            try:
                content = uploaded_file.getvalue().decode("utf-8")
                st.session_state.engine.parse(content, uploaded_file.name)
                st.session_state.knowledge_base = content
                st.success(f"Loaded {uploaded_file.name}")
                st.experimental_rerun()
            except Exception as e:
                st.error(f"Error loading file: {e}")
        
        # Advanced features
        st.subheader("Advanced Features")
        debug_mode = st.checkbox("Enable Debugger", value=st.session_state.engine.debugger_active)
        if debug_mode != st.session_state.engine.debugger_active:
            st.session_state.engine.debugger_active = debug_mode
        
        parallel_mode = st.checkbox("Enable Parallel Execution", value=st.session_state.engine.parallel_enabled)
        if parallel_mode != st.session_state.engine.parallel_enabled:
            st.session_state.engine.parallel_enabled = parallel_mode
        
        trace_mode = st.checkbox("Enable Tracing", value=st.session_state.engine.trace_enabled)
        if trace_mode != st.session_state.engine.trace_enabled:
            st.session_state.engine.trace_enabled = trace_mode
        
        # Statistics
        st.subheader("Statistics")
        if st.button("Show Statistics"):
            stats = st.session_state.engine.stats()
            st.json(stats)
    
    # Main content area
    tab1, tab2, tab3, tab4 = st.tabs(["Knowledge Base", "Query", "Advanced Features", "Help"])
    
    with tab1:
        st.header("Knowledge Base")
        
        # Text editor for knowledge base
        knowledge_base = st.text_area(
            "Enter your Prolog-like code here (facts, rules, DCGs):",
            value=st.session_state.knowledge_base,
            height=300
        )
        
        if st.button("Update Knowledge Base"):
            try:
                st.session_state.engine.clear()
                st.session_state.engine.parse(knowledge_base, "input")
                st.session_state.knowledge_base = knowledge_base
                st.session_state.engine.optimize()
                st.success("Knowledge base updated successfully!")
            except Exception as e:
                st.error(f"Error updating knowledge base: {e}")
        
        # Display current knowledge base
        st.subheader("Current Knowledge Base")
        with st.expander("Facts"):
            facts_data = []
            for pred, facts in st.session_state.engine.facts.items():
                for fact in facts:
                    args_str = ", ".join([format_term(arg) for arg in fact])
                    facts_data.append({"Predicate": pred, "Arguments": args_str})
            
            if facts_data:
                st.dataframe(pd.DataFrame(facts_data))
            else:
                st.write("No facts in the knowledge base.")
        
        with st.expander("Rules"):
            rules_data = []
            for rule in st.session_state.engine.rules:
                head_name, head_args, body_parts = rule
                head_str = f"{head_name}({', '.join([format_term(arg) for arg in head_args])})"
                body_str = ", ".join([f"{name}({', '.join([format_term(arg) for arg in args])})" for name, args in body_parts])
                rules_data.append({"Head": head_str, "Body": body_str})
            
            if rules_data:
                st.dataframe(pd.DataFrame(rules_data))
            else:
                st.write("No rules in the knowledge base.")
    
    with tab2:
        st.header("Query")
        
        # Query input
        query = st.text_input("Enter your query (e.g., ?- ancestor(john, X).):")
        
        # Query options
        col1, col2 = st.columns(2)
        with col1:
            max_solutions = st.number_input("Max Solutions", min_value=1, value=10)
        with col2:
            timeout = st.number_input("Timeout (seconds)", min_value=1, value=30)
        
        if st.button("Run Query"):
            if query:
                try:
                    # Capture output for tracing
                    output_buffer = io.StringIO()
                    with redirect_stdout(output_buffer):
                        start_time = time.time()
                        solutions = []
                        
                        for solution in st.session_state.engine.query(query, max_solutions, timeout):
                            solutions.append(solution)
                        
                        duration = time.time() - start_time
                    
                    # Display trace output if enabled
                    if st.session_state.engine.trace_enabled:
                        trace_output = output_buffer.getvalue()
                        if trace_output:
                            st.subheader("Trace Output")
                            st.code(trace_output)
                    
                    # Display solutions
                    st.subheader(f"Solutions ({len(solutions)} found in {duration:.3f}s)")
                    
                    if solutions:
                        # Extract variable names from the query
                        var_names = list(set(re.findall(r'\b[A-Z]\w*\b', query)))
                        
                        if var_names:
                            # Create a dataframe with solutions
                            solutions_data = []
                            for i, solution in enumerate(solutions):
                                row = {"Solution": i + 1}
                                for var in var_names:
                                    if var in solution:
                                        row[var] = format_term(substitute(var, solution))
                                    else:
                                        row[var] = "N/A"
                                solutions_data.append(row)
                            
                            st.dataframe(pd.DataFrame(solutions_data))
                        else:
                            st.write("Yes")
                    else:
                        st.write("No solutions found.")
                    
                    # Add to query history
                    st.session_state.query_history.append({
                        "query": query,
                        "solutions": len(solutions),
                        "time": duration
                    })
                except Exception as e:
                    st.error(f"Error executing query: {e}")
                    st.code(traceback.format_exc())
            else:
                st.warning("Please enter a query.")
        
        # Query history
        if st.session_state.query_history:
            st.subheader("Query History")
            history_data = pd.DataFrame(st.session_state.query_history)
            st.dataframe(history_data)
    
    with tab3:
        st.header("Advanced Features")
        
        feature_tab1, feature_tab2, feature_tab3, feature_tab4, feature_tab5, feature_tab6 = st.tabs([
            "Tabling", "Foreign Functions", "Debugger", "DCGs", "Constraints", "Parallel Execution"
        ])
        
        with feature_tab1:
            st.subheader("Tabling/Memoization")
            st.write("Tabling caches the results of predicate calls to avoid redundant computation and solve infinite recursion problems.")
            
            # Tabled predicates
            tabled_preds = st.multiselect(
                "Select predicates to table:",
                options=list(set([f"{pred}/{len(facts[0])}" for pred, facts in st.session_state.engine.facts.items() if facts] +
                                [f"{rule[0]}/{len(rule[1])}" for rule in st.session_state.engine.rules])),
                default=[pred for pred in st.session_state.engine.tabled_predicates]
            )
            
            if st.button("Update Tabled Predicates"):
                st.session_state.engine.tabled_predicates = set(tabled_preds)
                st.success("Tabled predicates updated!")
            
            # Add new tabled predicate
            with st.expander("Add New Tabled Predicate"):
                new_pred = st.text_input("Predicate (e.g., ancestor/2):")
                if st.button("Add Tabled Predicate") and new_pred:
                    st.session_state.engine.tabled_predicates.add(new_pred)
                    st.success(f"Added {new_pred} to tabled predicates.")
                    st.experimental_rerun()
            
            # Current tabled predicates
            if st.session_state.engine.tabled_predicates:
                st.write("Current tabled predicates:")
                for pred in st.session_state.engine.tabled_predicates:
                    st.write(f"- {pred}")
            else:
                st.write("No predicates are currently tabled.")
        
        with feature_tab2:
            st.subheader("Foreign Function Interface")
            st.write("Call Python functions directly from your logic programs.")
            
            # Registered foreign functions
            if st.session_state.engine.foreign_functions:
                st.write("Registered foreign functions:")
                for (name, arity), func in st.session_state.engine.foreign_functions.items():
                    st.write(f"- {name}/{arity}: {func.__name__}")
            else:
                st.write("No foreign functions registered.")
            
            # Add new foreign function
            with st.expander("Register New Foreign Function"):
                func_name = st.text_input("Function Name:")
                func_code = st.text_area("Python Code (def my_func(...): ...):", height=150)
                
                if st.button("Register Function") and func_name and func_code:
                    try:
                        # Execute the code to define the function
                        exec(func_code, globals())
                        # Get the function object
                        func = globals()[func_name]
                        # Register it with a default arity of 3
                        st.session_state.engine.register_foreign(f"{func_name}/3", func)
                        st.success(f"Registered {func_name}/3")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Error registering function: {e}")
        
        with feature_tab3:
            st.subheader("Debugger")
            st.write("Step-by-step debugging to inspect variable bindings and control execution flow.")
            
            # Debugger controls
            debugger_active = st.checkbox("Enable Debugger", value=st.session_state.engine.debugger_active)
            if debugger_active != st.session_state.engine.debugger_active:
                st.session_state.engine.debugger_active = debugger_active
            
            # Breakpoints
            with st.expander("Breakpoints"):
                # Get all predicates
                all_preds = list(set([f"{pred}/{len(facts[0])}" for pred, facts in st.session_state.engine.facts.items() if facts] +
                                    [f"{rule[0]}/{len(rule[1])}" for rule in st.session_state.engine.rules]))
                
                breakpoints = st.multiselect(
                    "Select breakpoints:",
                    options=all_preds,
                    default=list(st.session_state.engine.breakpoints)
                )
                
                if st.button("Update Breakpoints"):
                    st.session_state.engine.breakpoints = set(breakpoints)
                    st.success("Breakpoints updated!")
            
            # Current breakpoints
            if st.session_state.engine.breakpoints:
                st.write("Current breakpoints:")
                for bp in st.session_state.engine.breakpoints:
                    st.write(f"- {bp}")
            else:
                st.write("No breakpoints set.")
        
        with feature_tab4:
            st.subheader("Definite Clause Grammars (DCGs)")
            st.write("Special syntax for writing parsers and grammars, making NLP tasks much easier.")
            
            # DCG rules
            dcg_rules = [rule for rule in st.session_state.engine.rules if len(rule[1]) == 2]
            
            if dcg_rules:
                st.write("DCG Rules:")
                for rule in dcg_rules:
                    head_name, _, body_parts = rule
                    st.write(f"- {head_name} --> {body_parts}")
            else:
                st.write("No DCG rules found.")
            
            # DCG example
            with st.expander("DCG Example"):
                st.code("""
sentence --> noun_phrase, verb_phrase.
noun_phrase --> determiner, noun.
verb_phrase --> verb.
determiner --> [the].
noun --> [cat]. noun --> [dog].
verb --> [sleeps]. verb --> [runs].

% Query example:
% ?- phrase(sentence, [the, cat, sleeps], []).
                """)
        
        with feature_tab5:
            st.subheader("Constraints (CLP(FD))")
            st.write("Finite Domain constraints to solve problems with relational constraints.")
            
            # Constraint example
            with st.expander("Constraint Example"):
                st.code("""
% Magic Square example
magic_square([[A,B,C],[D,E,F],[G,H,I]]) :-
    [A,B,C,D,E,F,G,H,I] ins 1..9,
    all_different([A,B,C,D,E,F,G,H,I]),
    A+B+C #= 15, D+E+F #= 15, G+H+I #= 15,
    A+D+G #= 15, B+E+H #= 15, C+F+I #= 15,
    A+E+I #= 15, C+E+G #= 15.

% Query example:
% ?- magic_square(Square), labeling([], Square).
                """)
            
            # Constraint store
            if st.session_state.engine.constraint_store:
                st.write("Current Constraint Store:")
                for var, domain in st.session_state.engine.constraint_store.items():
                    st.write(f"- {var}: {domain}")
            else:
                st.write("No constraints in the store.")
        
        with feature_tab6:
            st.subheader("Parallel Execution")
            st.write("Run independent search branches in parallel, leveraging multi-core processors.")
            
            # Parallel execution controls
            parallel_enabled = st.checkbox("Enable Parallel Execution", value=st.session_state.engine.parallel_enabled)
            if parallel_enabled != st.session_state.engine.parallel_enabled:
                st.session_state.engine.parallel_enabled = parallel_enabled
            
            # Thread pool info
            if st.session_state.engine.parallel_enabled:
                st.write(f"Parallel execution is enabled with {os.cpu_count() or 4} worker threads.")
            else:
                st.write("Parallel execution is disabled.")
    
    with tab4:
        st.header("Help")
        
        help_tab1, help_tab2, help_tab3 = st.tabs(["Syntax", "Features", "Examples"])
        
        with help_tab1:
            st.subheader("Syntax")
            st.markdown("""
            **Facts:**
            ```
            parent(john, mary).
            male(john).
            ```
            
            **Rules:**
            ```
            ancestor(X, Y) :- parent(X, Y).
            ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).
            ```
            
            **DCGs (Definite Clause Grammars):**
            ```
            sentence --> noun_phrase, verb_phrase.
            noun_phrase --> determiner, noun.
            ```
            
            **Queries:**
            ```
            ?- ancestor(john, X).
            ```
            """)
        
        with help_tab2:
            st.subheader("Features")
            st.markdown("""
            **Tabling/Memoization:**
            - Caches results of predicate calls
            - Prevents redundant computation
            - Solves infinite recursion problems
            
            **Foreign Function Interface:**
            - Call Python functions from Prolog
            - Extend functionality with custom code
            
            **Debugger:**
            - Step-by-step execution
            - Set breakpoints
            - Inspect variable bindings
            
            **DCGs (Definite Clause Grammars):**
            - Natural language processing
            - Parser generation
            
            **Constraints (CLP(FD)):**
            - Relational problem solving
            - Finite domain constraints
            
            **Parallel Execution:**
            - Multi-core processing
            - Faster query resolution
            """)
        
        with help_tab3:
            st.subheader("Examples")
            st.markdown("""
            **Family Relationships:**
            ```
            parent(john, mary).
            parent(mary, susan).
            male(john).
            female(mary).
            
            father(X, Y) :- parent(X, Y), male(X).
            ```
            
            **List Processing:**
            ```
            member(X, [X|_]).
            member(X, [_|T]) :- member(X, T).
            
            append([], L, L).
            append([H|T], L, [H|R]) :- append(T, L, R).
            ```
            
            **Constraints:**
            ```
            sudoku(Rows) :-
                Rows ins 1..9,
                maplist(all_different, Rows),
                transpose(Rows, Cols),
                maplist(all_different, Cols),
                Rows = [A,B,C,D,E,F,G,H,I],
                blocks(A,B,C,D,E,F,G,H,I),
                labeling([], Rows).
            ```
            """)

def preload_examples():
    """Load example knowledge base into the session state engine."""
    examples = """
    % Family relationships
    parent(john, mary).
    parent(mary, susan).
    parent(john, mark).
    parent(mark, alice).
    parent(susan, bob).
    
    male(john).
    male(mark).
    male(bob).
    female(mary).
    female(susan).
    female(alice).
    
    % Recursive rules (good for tabling)
    ancestor(X, Y) :- parent(X, Y).
    ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).
    
    % Derived relationships
    father(X, Y) :- parent(X, Y), male(X).
    mother(X, Y) :- parent(X, Y), female(X).
    grandparent(X, Y) :- parent(X, Z), parent(Z, Y).
    
    % List operations
    member(X, [X|_]).
    member(X, [_|T]) :- member(X, T).
    
    append([], L, L).
    append([H|T], L, [H|R]) :- append(T, L, R).
    
    length([], 0).
    length([_|T], N) :- length(T, M), N is M + 1.
    
    % DCG Example
    sentence --> noun_phrase, verb_phrase.
    noun_phrase --> determiner, noun.
    verb_phrase --> verb.
    determiner --> [the].
    noun --> [cat]. noun --> [dog].
    verb --> [sleeps]. verb --> [runs].
    
    % Constraint Example
    magic_square([[A,B,C],[D,E,F],[G,H,I]]) :-
        [A,B,C,D,E,F,G,H,I] ins 1..9,
        all_different([A,B,C,D,E,F,G,H,I]),
        A+B+C #= 15, D+E+F #= 15, G+H+I #= 15,
        A+D+G #= 15, B+E+H #= 15, C+F+I #= 15,
        A+E+I #= 15, C+E+G #= 15.
    """
    
    st.session_state.engine.parse(examples, "examples")
    st.session_state.knowledge_base = examples
    st.session_state.engine.optimize()

if __name__ == "__main__":
    streamlit_app()