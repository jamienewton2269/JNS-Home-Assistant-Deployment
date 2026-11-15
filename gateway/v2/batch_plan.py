"""Bounded dependency-aware batch planning; deliberately never executes commands."""
from collections import deque

MAX_STEPS = 16
KINDS = frozenset({"health", "capabilities", "git_status", "test", "build"})

class BatchRejected(ValueError):
    pass

def plan(steps):
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise BatchRejected("invalid_step_count")
    names = set()
    graph = {}
    ordered = {}
    for step in steps:
        if not isinstance(step, dict) or set(step) != {"id", "kind", "after"}:
            raise BatchRejected("invalid_step")
        sid, kind, deps = step["id"], step["kind"], step["after"]
        if not isinstance(sid, str) or not sid.isascii() or not sid.replace("_", "").isalnum() or not 1 <= len(sid) <= 40 or sid in names:
            raise BatchRejected("invalid_or_duplicate_id")
        if kind not in KINDS or not isinstance(deps, list) or len(deps) > MAX_STEPS or any(not isinstance(d, str) for d in deps) or len(set(deps)) != len(deps):
            raise BatchRejected("invalid_kind_or_dependencies")
        names.add(sid)
        ordered[sid] = step
        graph[sid] = deps
    if any(d not in names for deps in graph.values() for d in deps):
        raise BatchRejected("unknown_dependency")
    result = []
    ready = deque(s for s in ordered if not graph[s])
    while ready:
        sid = ready.popleft()
        result.append(ordered[sid])
        for child in ordered:
            if sid in graph[child]:
                graph[child] = [d for d in graph[child] if d != sid]
                if not graph[child] and child not in {x["id"] for x in result} and child not in ready:
                    ready.append(child)
    if len(result) != len(steps):
        raise BatchRejected("dependency_cycle")
    return result
