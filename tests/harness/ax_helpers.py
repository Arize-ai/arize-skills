"""
Helper functions for setup/teardown using the ax CLI.

All functions are synchronous (subprocess.run) since they are called
from pytest fixtures, not from async test bodies.
"""

import json
import os
import subprocess
import tempfile
from typing import Any


def ax_run(args: list[str], timeout: int = 60) -> Any:
    """Run an ax CLI command and return parsed JSON output."""
    cmd = ["ax"] + args + ["-o", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ax command failed: {' '.join(cmd)}\n"
            f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
        )
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def create_dataset(
    name: str, space_id: str, examples: list[dict[str, Any]]
) -> str:
    """Create a dataset and return its ID."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(examples, f)
        tmp_path = f.name

    try:
        result = ax_run(
            [
                "datasets",
                "create",
                "--name",
                name,
                "--space-id",
                space_id,
                "--file",
                tmp_path,
            ]
        )
        return result["id"]
    finally:
        os.unlink(tmp_path)


def delete_dataset(dataset_id: str) -> None:
    """Delete a dataset."""
    subprocess.run(
        ["ax", "datasets", "delete", dataset_id, "--force"],
        capture_output=True,
        timeout=30,
    )


def export_dataset(dataset_id: str) -> list[dict[str, Any]]:
    """Export a dataset's examples as a list of dicts."""
    proc = subprocess.run(
        ["ax", "datasets", "export", dataset_id, "--stdout"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(proc.stdout)


def create_experiment(
    name: str, dataset_id: str, runs: list[dict[str, Any]]
) -> str:
    """Create an experiment with runs and return its ID."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(runs, f)
        tmp_path = f.name

    try:
        result = ax_run(
            [
                "experiments",
                "create",
                "--name",
                name,
                "--dataset-id",
                dataset_id,
                "--file",
                tmp_path,
            ]
        )
        return result["id"]
    finally:
        os.unlink(tmp_path)


def delete_experiment(experiment_id: str) -> None:
    """Delete an experiment."""
    subprocess.run(
        ["ax", "experiments", "delete", experiment_id, "--force"],
        capture_output=True,
        timeout=30,
    )


def list_datasets(space_id: str | None = None) -> list[dict[str, Any]]:
    """List datasets, optionally filtered by space."""
    args = ["datasets", "list"]
    if space_id:
        args += ["--space-id", space_id]
    return ax_run(args)


def list_experiments(dataset_id: str | None = None) -> list[dict[str, Any]]:
    """List experiments, optionally filtered by dataset."""
    args = ["experiments", "list"]
    if dataset_id:
        args += ["--dataset-id", dataset_id]
    return ax_run(args)


def export_traces(
    project: str,
    space_id: str,
    filter_expr: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Export traces via ax CLI."""
    args = [
        "traces",
        "export",
        project,
        "--space-id",
        space_id,
        "-l",
        str(limit),
        "--stdout",
    ]
    if filter_expr:
        args += ["--filter", filter_expr]
    proc = subprocess.run(
        ["ax"] + args, capture_output=True, text=True, timeout=120
    )
    return json.loads(proc.stdout) if proc.stdout.strip() else []
