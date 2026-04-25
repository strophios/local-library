"""Long-running daemon wrapping the Library orchestrator as a socket service.

Exposes a Unix-domain-socket JSON-RPC 2.0 server over the existing Library,
keeping the embedder and sqlite-vec connection warm in memory for sub-500 ms
warm search latency.
"""

# pattern: Imperative Shell (asyncio, sockets, Library lifecycle)
