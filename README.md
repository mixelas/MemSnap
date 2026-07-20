# Lightweight Cache Engine in Python

A compact, interview-style cache server that implements core systems concepts in a single, readable Python implementation: hash-based storage, TTL handling, eviction policies, socket I/O, and persistence.

## Why this project stands out

This project is designed to showcase strong fundamentals in data structures and systems design:

- a hash map backed cache with constant-time lookup semantics
- eviction strategies that reflect real-world cache tradeoffs
- lazy TTL expiration to avoid unnecessary full-store scans
- a simple network protocol over TCP sockets
- a persistence layer that batches writes instead of forcing disk I/O on every access

It is a strong example for engineers interviewing for backend, infrastructure, distr`ibuted systems, or platform roles because it demonstrates both algorithmic thinking and practical engineering judgment.

## What the system implements

The server supports:

- `SET <key> <value> <ttl_seconds>`
- `GET <key>`
- `QUIT`

It also supports two eviction policies:

### LRU: Least Recently Used

LRU keeps the most recently accessed items and evicts the one that has gone the longest without being touched.

Use cases:
- workloads with temporal locality
- web caching and request replay patterns

### LFU: Least Frequently Used

LFU preserves items that have been accessed most often and evicts the least frequently touched entry.

Use cases:
- repeated hot-key workloads
- read-heavy workloads where frequency matters more than recency

## Data structure choices

### LRU implementation

- uses an ordered dictionary to preserve access recency
- `GET` updates the access position in `O(1)`
- eviction is `O(1)` because the oldest item is the leftmost entry

### LFU implementation

- uses frequency buckets keyed by access count
- `GET` increments the access frequency and reassigns the entry to the next bucket
- eviction uses a running minimum-frequency tracker so the least-frequent bucket is found without scanning all bucket levels

## Complexity

| Operation | Complexity | Notes |
|---|---|---|
| `GET` | `O(1)` | direct lookup with lazy TTL validation on the requested key |
| `SET` | `O(1)` amortized | insertion and eviction are constant-time in the implemented structures |
| LRU eviction | `O(1)` | uses the front of the ordered structure |
| LFU eviction | `O(1)` | uses the tracked minimum-frequency bucket |
| persistence flush | `O(n)` | deferred to avoid blocking normal cache operations |

## Why it is interesting from an interview perspective

This project shows that you can think beyond “just implement a cache.” It demonstrates:

- algorithmic tradeoffs between recency-based and frequency-based eviction
- the difference between correctness and performance in systems code
- careful design around mutation, expiration, and persistence
- awareness of I/O cost and the importance of batching writes

## Running the server

Start the server with:

```bash
python server.py --port 6380 --db cache_state.json --max-entries 100 --policy lru
```

Example interaction:

```bash
printf "SET alpha 42 60\n" | nc 127.0.0.1 6380
printf "GET alpha\n" | nc 127.0.0.1 6380
```

## Testing

Run the regression suite:

```bash
python -m unittest discover -s tests -v
```

## Project structure

- `server.py` — cache engine and TCP server
- `tests/test_cache.py` — behavior tests for TTL, eviction, and persistence
- `README.md` — design, tradeoffs, and usage

## Quick demo with bundled client

`client.py` is a tiny REPL that opens a fresh TCP connection per command (the server expects one-shot connections).

Usage:

```bash
python client.py --port 6380
# then at the prompt:
> SET a 1 30
OK
> GET a
1
> QUIT
OK
```

You can also send a single command non-interactively:

```bash
python client.py --port 6380 --cmd "SET x 42 60"
```

## Bottom line

This is a compact but technically rich cache engine that communicates strong engineering depth without relying on frameworks or boilerplate. It is the kind of project that makes technical interview conversations much easier because the implementation choices are concrete, explainable, and measurable.
