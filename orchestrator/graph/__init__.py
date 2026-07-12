"""Project state machine (LangGraph).

TODO: build the graph from config/orchestrator.yaml — nodes are workflow stages /
agent roles, edges are transitions incl. loop-backs and approval gates, with
Postgres checkpointing so projects survive restarts. See docs/05 and docs/09.
"""
