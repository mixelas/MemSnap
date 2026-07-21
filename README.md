# Lightweight Cache Engine in Python

A compact cache server that implements core systems concepts in a readable Python implementation: hash-based storage, TTL handling, eviction policies, socket I/O, and persistence.

## Design goals

This implementation focuses on clarity and correctness for:

- in-memory key-value storage with optional expiration
- configurable eviction policies (LRU and LFU)
- a simple TCP command protocol for GET/SET/QUIT
- deferred persistence to reduce write amplification
- concurrency using thread-per-connection socket handling

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

## Engineering considerations

The implementation reflects several practical tradeoffs:

- recency-based eviction (LRU) versus frequency-based eviction (LFU)
- lazy TTL expiration to avoid full-store scans on every access
- a persistence model that batches writes rather than flushing on every mutation
- a thread-per-connection server model that keeps socket handling simple

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

