#!/usr/bin/env python3
"""Karmi migration rollback rehearsal; runs with Karmi's interpreter against a disposable database.

Walks the whole revision chain down to the first revision and back up, comparing the reflected
schema at every level, checks model/schema agreement at head, and proves the destructive base
downgrade refuses without its explicit opt-in. Prints one JSON object; never touches a shared DB.
"""
from __future__ import annotations

import json
import os
import sys

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect


def snapshot(url: str) -> dict[str, object]:
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        tables = sorted(name for name in inspector.get_table_names() if name != "alembic_version")
        return {table: {
            "columns": sorted(f"{c['name']}:{c['type']}:{c['nullable']}" for c in inspector.get_columns(table)),
            "indexes": sorted(str(index["name"]) for index in inspector.get_indexes(table)),
            "unique": sorted(str(unique["name"]) for unique in inspector.get_unique_constraints(table)),
            "foreign_keys": sorted(f"{fk['referred_table']}:{fk['constrained_columns']}:{fk.get('options')}"
                                   for fk in inspector.get_foreign_keys(table)),
        } for table in tables}
    finally:
        engine.dispose()


def main() -> int:
    url = os.environ["DAILY_AGENT_DATABASE_URL"]
    config = Config("alembic.ini")
    chain = [revision.revision for revision in ScriptDirectory.from_config(config).walk_revisions()]
    head, first = chain[0], chain[-1]
    checks: dict[str, bool] = {}
    command.upgrade(config, "head")
    snapshots = {head: snapshot(url)}
    for lower in chain[1:]:
        command.downgrade(config, lower)
        snapshots[lower] = snapshot(url)
    mismatched: list[str] = []
    for higher in reversed(chain[:-1]):
        command.upgrade(config, higher)
        if snapshot(url) != snapshots[higher]:
            mismatched.append(higher)
    checks["every_revision_round_trips"] = not mismatched
    command.check(config)  # raises on model/schema drift at head
    checks["head_matches_models"] = True

    command.downgrade(config, first)
    os.environ.pop("DAILY_AGENT_ALLOW_DESTRUCTIVE_DOWNGRADE", None)
    try:
        command.downgrade(config, "base")
        refused = False
    except Exception:  # the initial revision raises its own guard error
        refused = True
    checks["destructive_base_downgrade_refused"] = refused and snapshot(url) == snapshots[first]
    command.upgrade(config, "head")
    checks["restored_to_head"] = snapshot(url) == snapshots[head]
    print(json.dumps({"checks": checks, "revisions": len(chain), "head": head,
                      "mismatched_revisions": mismatched,
                      "tables_dropped_by_head_rollback": sorted(set(snapshots[head]) - set(snapshots[chain[1]]))}))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
