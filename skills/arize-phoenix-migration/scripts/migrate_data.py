#!/usr/bin/env python3
"""Export Phoenix datasets/experiments/evaluations and verify them in AX."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from itertools import pairwise
from pathlib import Path

from dotenv import dotenv_values


class DataMigrationError(Exception):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def serializable(value):
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return {str(k): serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return serializable(value.model_dump(mode="json"))
    return value


def checksum(payload):
    return hashlib.sha256(canonical(payload).encode()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(canonical(value) + "\n")
    temporary.replace(path)
    path.chmod(0o600)


def load(path):
    manifest = json.loads(Path(path).read_text())
    digest = manifest.pop("checksum", None)
    if digest != checksum(manifest):
        raise DataMigrationError("Data manifest checksum does not match its contents.")
    manifest["checksum"] = digest
    return manifest


def save_manifest(path, manifest):
    raw = {k: v for k, v in manifest.items() if k != "checksum"}
    manifest["checksum"] = checksum(raw)
    save(path, manifest)


def configuration(env_file=None):
    values = dict(dotenv_values(env_file)) if env_file else {}
    values.update(os.environ)
    if not values.get("ARIZE_SPACE_ID") and values.get("ARIZE_SPACE"):
        values["ARIZE_SPACE_ID"] = values["ARIZE_SPACE"]
    return {k: v for k, v in values.items() if v}


def require(config, names):
    missing = [name for name in names if not config.get(name)]
    if missing:
        raise DataMigrationError("Missing configuration: " + ", ".join(missing))


def unique_index(rows, identity, label):
    indexed = {}
    for row in rows:
        key = identity(row)
        if not key:
            raise DataMigrationError(f"{label} has a missing source identity.")
        if key in indexed:
            raise DataMigrationError(f"{label} has duplicate source identity {key}.")
        indexed[key] = row
    return indexed


def evaluation_provenance(result):
    return canonical(
        {
            "phoenix_evaluation_id": result.get("id"),
            "phoenix_annotator_kind": result.get("annotator_kind"),
            "phoenix_trace_id": result.get("trace_id"),
            "phoenix_metadata": result.get("metadata") or {},
            "phoenix_error": result.get("error"),
            "phoenix_start_time": result.get("start_time"),
            "phoenix_end_time": result.get("end_time"),
        }
    )


def validate_source_dataset(source):
    versions = source["versions"]
    if not versions:
        raise DataMigrationError(f"Dataset {source['name']} has no versions.")
    version_ids = unique_index(
        versions, lambda version: version.get("id"), f"Dataset {source['name']} versions"
    )
    version_example_ids = []
    for version in versions:
        examples = unique_index(
            version["examples"],
            lambda example: example.get("source_global_id"),
            f"Dataset {source['name']} version {version['id']} examples",
        )
        version_example_ids.append(set(examples))
    if not version_example_ids[0]:
        raise DataMigrationError(
            f"Dataset {source['name']} has an empty initial version."
        )
    for index, (previous, current) in enumerate(
        pairwise(version_example_ids), 2
    ):
        if not previous & current:
            raise DataMigrationError(
                f"Dataset {source['name']} version {index} has no retained example to fork in AX."
            )
    experiments = unique_index(
        source["experiments"],
        lambda experiment: experiment.get("id"),
        f"Dataset {source['name']} experiments",
    )
    unique_index(
        source["experiments"],
        lambda experiment: experiment.get("name"),
        f"Dataset {source['name']} experiment names",
    )
    latest_version_id = versions[-1]["id"] if versions else None
    for experiment in experiments.values():
        version_id = experiment.get("dataset_version_id")
        if version_id not in version_ids:
            raise DataMigrationError(
                f"Experiment {experiment['name']} references unknown dataset version {version_id}."
            )
        if version_id != latest_version_id:
            raise DataMigrationError(
                f"Experiment {experiment['name']} references older dataset version {version_id}; AX import cannot preserve that relationship."
            )
        task_runs = unique_index(
            experiment["task_runs"],
            lambda run: run.get("id"),
            f"Experiment {experiment['name']} task runs",
        )
        for result in experiment["evaluation_runs"]:
            if not result.get("experiment_run_id") or not result.get("name"):
                raise DataMigrationError(
                    f"Experiment {experiment['name']} evaluation has a missing run ID or name."
                )
        evaluations = unique_index(
            experiment["evaluation_runs"],
            lambda result: (result.get("experiment_run_id"), result.get("name")),
            f"Experiment {experiment['name']} evaluations",
        )
        for run_id, _ in evaluations:
            if run_id not in task_runs:
                raise DataMigrationError(
                    f"Experiment {experiment['name']} evaluation references unknown task run {run_id}."
                )


def validate_manifest_sources(manifest):
    datasets = unique_index(
        manifest["datasets"],
        lambda dataset: dataset.get("id"),
        "Phoenix datasets",
    )
    unique_index(
        manifest["datasets"],
        lambda dataset: dataset.get("name"),
        "Phoenix dataset names",
    )
    for source in datasets.values():
        validate_source_dataset(source)


def experiment_run_provenance(_experiment, run):
    return {
        "phoenix_experiment_run_id": run["id"],
        "phoenix_trace_id": run.get("trace_id"),
        "phoenix_repetition_number": run.get("repetition_number"),
        "phoenix_error": run.get("error"),
        "phoenix_start_time": run.get("start_time"),
        "phoenix_end_time": run.get("end_time"),
    }


def phoenix_client(config):
    from phoenix.client import Client

    return Client(
        base_url=config["PHOENIX_BASE_URL"], api_key=config.get("PHOENIX_API_KEY")
    )


def ax_client(config):
    from migrate import sdk_client

    return sdk_client(config)


def list_all(method, field, **kwargs):
    rows = []
    cursor = None
    seen = set()
    while True:
        response = method(cursor=cursor, **kwargs)
        rows.extend(getattr(response, field))
        pagination = getattr(response, "pagination", None)
        if not pagination or not pagination.has_more:
            return rows
        cursor = pagination.next_cursor
        if not cursor or cursor in seen:
            raise DataMigrationError(f"AX {field} pagination did not advance.")
        seen.add(cursor)


def exact_datasets(client, name, space):
    return [
        item
        for item in list_all(client.datasets.list, "datasets", name=name, space=space)
        if item.name == name
    ]


def exact_experiments(client, dataset_id, name):
    return [
        item
        for item in list_all(
            client.experiments.list, "experiments", dataset=dataset_id
        )
        if item.name == name
    ]


def example_record(example):
    return {
        "source_id": example.get("id"),
        "source_global_id": example.get("node_id") or example.get("id"),
        "input": serializable(example.get("input") or {}),
        "output": serializable(example.get("output") or {}),
        "metadata": serializable(example.get("metadata") or {}),
    }


def export_data(config, path, selected=None):
    require(config, ["PHOENIX_BASE_URL"])
    client = phoenix_client(config)
    wanted = set(selected or [])
    datasets = []
    for summary in client.datasets.list():
        if wanted and summary["name"] not in wanted and summary["id"] not in wanted:
            continue
        versions = []
        source_versions = client.datasets.get_dataset_versions(
            dataset=summary, limit=100
        )
        if len(source_versions) == 100:
            raise DataMigrationError(
                f"Dataset {summary['name']} has at least 100 versions; complete pagination is not available through this client."
            )
        for version in reversed(source_versions):
            snapshot = client.datasets.get_dataset(
                dataset=summary["id"], version_id=version["version_id"]
            )
            versions.append(
                {
                    "id": version["version_id"],
                    "created_at": serializable(version.get("created_at")),
                    "description": version.get("description"),
                    "metadata": serializable(version.get("metadata") or {}),
                    "examples": [example_record(e) for e in snapshot.examples],
                }
            )
        experiments = []
        for experiment in client.experiments.list(dataset_id=summary["id"]):
            detail = client.experiments.get_experiment(experiment_id=experiment["id"])
            experiments.append(
                {
                    "id": detail["experiment_id"],
                    "name": experiment.get("name") or detail.get("project_name"),
                    "dataset_version_id": detail.get("dataset_version_id"),
                    "metadata": serializable(detail.get("experiment_metadata") or {}),
                    "task_runs": serializable(detail.get("task_runs") or []),
                    "evaluation_runs": serializable(
                        detail.get("evaluation_runs") or []
                    ),
                }
            )
        datasets.append(
            {
                "id": summary["id"],
                "name": summary["name"],
                "description": summary.get("description"),
                "versions": versions,
                "experiments": experiments,
            }
        )
    if wanted:
        found = {d["name"] for d in datasets} | {d["id"] for d in datasets}
        missing = wanted - found
        if missing:
            raise DataMigrationError(
                "Phoenix datasets not found: " + ", ".join(sorted(missing))
            )
    manifest = {"schema": 1, "source": "phoenix", "datasets": datasets, "state": {}}
    manifest["checksum"] = checksum(manifest)
    save(path, manifest)
    return {
        "status": "exported",
        "dataset_count": len(datasets),
        "version_count": sum(len(d["versions"]) for d in datasets),
        "example_snapshot_count": sum(
            len(v["examples"]) for d in datasets for v in d["versions"]
        ),
        "experiment_count": sum(len(d["experiments"]) for d in datasets),
        "evaluation_count": sum(
            len(e["evaluation_runs"]) for d in datasets for e in d["experiments"]
        ),
    }


def ax_row(example):
    return {
        "phoenix_example_id": example["source_global_id"],
        "phoenix_custom_id": example["source_id"],
        "input_json": canonical(example["input"]),
        "output_json": canonical(example["output"]),
        "metadata_json": canonical(example["metadata"]),
    }


def destination_examples(client, dataset_id, version_id=None):
    examples = []
    cursor = None
    while True:
        response = client.datasets.list_examples(
            dataset=dataset_id,
            dataset_version_id=version_id,
            limit=100,
            cursor=cursor,
        )
        examples.extend(response.examples)
        if not response.pagination.has_more:
            break
        cursor = response.pagination.next_cursor
        if not cursor:
            raise DataMigrationError("AX dataset pagination omitted its next cursor.")
    return unique_index(
        examples,
        lambda example: example.additional_properties.get("phoenix_example_id"),
        f"AX dataset version {version_id or 'latest'} examples",
    )


def get_dataset_after_create(
    client, dataset, space=None, attempts=12, sleep=time.sleep
):
    last_error = None
    for attempt in range(attempts):
        try:
            return client.datasets.get(dataset=dataset, space=space)
        except Exception as error:  # noqa: BLE001 -- SDK surfaces several transport types
            last_error = error
            if attempt + 1 < attempts:
                sleep(2)
    raise DataMigrationError(
        f"AX dataset was created but was not readable after {attempts} attempts."
    ) from last_error


def replay_versions(client, dataset, source, space, state, checkpoint):
    versions = source["versions"]
    if not versions or not versions[0]["examples"]:
        raise DataMigrationError(
            f"Dataset {source['name']} has an empty initial version."
        )
    created = get_dataset_after_create(client, dataset.name, space)
    initial_version_id = created.versions[-1].id
    current = destination_examples(client, dataset.id, initial_version_id)
    version_map = state["version_ids"]
    version_map.setdefault(versions[0]["id"], initial_version_id)
    checkpoint()
    for index, version in enumerate(versions[1:], 2):
        target = unique_index(
            version["examples"],
            lambda example: example.get("source_global_id"),
            f"Dataset {source['name']} version {version['id']} examples",
        )
        version_id = version_map.get(version["id"])
        if version_id is None:
            version_name = f"phoenix-version-{index}"
            refreshed = get_dataset_after_create(client, dataset.name, space)
            matched = [v for v in refreshed.versions if v.name == version_name]
            if matched:
                version_id = matched[0].id
            else:
                common = sorted(set(current) & set(target))
                if not common:
                    raise DataMigrationError(
                        f"Dataset {source['name']} version {index} has no retained example to fork in AX."
                    )
                first = common[0]
                previous_version_id = version_map[versions[index - 2]["id"]]
                fork = client.datasets.update_examples(
                    dataset=dataset.id,
                    dataset_version_id=previous_version_id,
                    new_version=version_name,
                    examples=[{"id": current[first].id, **ax_row(target[first])}],
                )
                version_id = fork.dataset_version_id
            version_map[version["id"]] = version_id
            checkpoint()
        current = destination_examples(client, dataset.id, version_id)
        common = sorted(set(current) & set(target))
        updates = [{"id": current[key].id, **ax_row(target[key])} for key in common]
        if updates:
            client.datasets.update_examples(
                dataset=dataset.id, dataset_version_id=version_id, examples=updates
            )
        added = [ax_row(target[key]) for key in sorted(set(target) - set(current))]
        if added:
            client.datasets.append_examples(
                dataset=dataset.id, dataset_version_id=version_id, examples=added
            )
        removed = [current[key].id for key in sorted(set(current) - set(target))]
        if removed:
            client.datasets.delete_examples(
                dataset=dataset.id, dataset_version_id=version_id, example_ids=removed
            )
        current = destination_examples(client, dataset.id, version_id)
        if set(current) != set(target):
            raise DataMigrationError(
                f"Dataset {source['name']} version {index} did not reconcile after writes."
            )
        checkpoint()
    return version_map, current


def import_experiment(client, dataset, experiment, examples, prefix):
    from arize.experiments.evaluators.types import EvaluationResultFieldNames
    from arize.experiments.types import ExperimentTaskFieldNames

    evaluations = defaultdict(list)
    for result in experiment["evaluation_runs"]:
        evaluations[result["experiment_run_id"]].append(result)
    rows = []
    columns = {}
    for run in experiment["task_runs"]:
        source_example_id = run.get("dataset_example_id")
        if source_example_id not in examples:
            raise DataMigrationError(
                f"Experiment {experiment['name']} references an example absent from the imported latest dataset."
            )
        row = {
            "example_id": examples[source_example_id].id,
            "output": canonical(run.get("output")),
            **experiment_run_provenance(experiment, run),
        }
        seen_names = set()
        for result in evaluations[run["id"]]:
            name = result["name"]
            if name in seen_names:
                raise DataMigrationError(
                    f"Experiment {experiment['name']} run {run['id']} has duplicate evaluation name {name}."
                )
            seen_names.add(name)
            key = "px_eval_" + hashlib.sha256(name.encode()).hexdigest()[:12]
            value = result.get("result") or {}
            row[key + "_score"] = value.get("score")
            row[key + "_label"] = value.get("label")
            row[key + "_explanation"] = value.get("explanation")
            row[key + "_metadata"] = evaluation_provenance(result)
            columns[name] = EvaluationResultFieldNames(
                score=key + "_score",
                label=key + "_label",
                explanation=key + "_explanation",
                metadata={"phoenix_migration": key + "_metadata"},
            )
        rows.append(row)
    name = prefix + experiment["name"]
    return client.experiments.create(
        name=name,
        dataset=dataset.id,
        experiment_runs=rows,
        task_fields=ExperimentTaskFieldNames(example_id="example_id", output="output"),
        evaluator_columns=columns or None,
        force_http=True,
    )


def import_data(config, path, prefix):
    require(config, ["ARIZE_API_KEY", "ARIZE_SPACE_ID"])
    manifest = load(path)
    validate_manifest_sources(manifest)
    client = ax_client(config)
    state = manifest["state"]

    def checkpoint():
        save_manifest(path, manifest)

    for source in manifest["datasets"]:
        name = prefix + source["name"]
        entry = state.setdefault(
            source["id"],
            {
                "dataset_name": name,
                "dataset_id": None,
                "create_started": False,
                "version_ids": {},
                "experiments": [],
            },
        )
        # Upgrade manifests written by the first release of this helper. Those
        # manifests recorded created object IDs but did not include the fields
        # used by the resumable importer.
        entry.setdefault("dataset_name", name)
        entry.setdefault("create_started", bool(entry.get("dataset_id")))
        entry.setdefault("version_ids", {})
        entry.setdefault("experiments", [])
        pristine = (
            not entry["create_started"]
            and not entry["dataset_id"]
            and not entry["version_ids"]
            and not entry["experiments"]
        )
        if entry["dataset_name"] != name and pristine:
            entry["dataset_name"] = name
        elif entry["dataset_name"] != name:
            raise DataMigrationError(
                "The import prefix differs from the manifest's recorded destination."
            )
        existing = exact_datasets(client, name, config["ARIZE_SPACE_ID"])
        if entry["dataset_id"]:
            if not any(item.id == entry["dataset_id"] for item in existing):
                raise DataMigrationError(
                    f"Recorded destination dataset is not readable: {name}"
                )
            dataset = next(item for item in existing if item.id == entry["dataset_id"])
        elif len(existing) == 1 and entry["create_started"]:
            dataset = existing[0]
            entry["dataset_id"] = dataset.id
            checkpoint()
        elif entry["create_started"]:
            raise DataMigrationError(
                f"Destination dataset create response could not be reconciled: {name}"
            )
        elif existing:
            raise DataMigrationError(f"Destination dataset already exists: {name}")
        else:
            entry["create_started"] = True
            checkpoint()
            dataset = client.datasets.create(
                name=name,
                space=config["ARIZE_SPACE_ID"],
                examples=[ax_row(e) for e in source["versions"][0]["examples"]],
                force_http=True,
            )
            entry["dataset_id"] = dataset.id
            checkpoint()
        version_map, examples = replay_versions(
            client, dataset, source, config["ARIZE_SPACE_ID"], entry, checkpoint
        )
        imported_experiments = entry["experiments"]
        for experiment in source["experiments"]:
            mapping = next(
                (x for x in imported_experiments if x["source_id"] == experiment["id"]),
                None,
            )
            destination_name = prefix + experiment["name"]
            if mapping:
                recorded = client.experiments.get(experiment=mapping["id"])
                if recorded.name != destination_name:
                    raise DataMigrationError(
                        f"Recorded destination experiment is missing or ambiguous: {destination_name}"
                    )
                continue
            matched = exact_experiments(client, dataset.id, destination_name)
            if len(matched) == 1:
                result = matched[0]
            elif matched:
                raise DataMigrationError(
                    f"Multiple destination experiments match: {destination_name}"
                )
            else:
                result = import_experiment(
                    client, dataset, experiment, examples, prefix
                )
            imported_experiments.append(
                {"source_id": experiment["id"], "id": result.id}
            )
            checkpoint()
        entry["version_ids"] = version_map
        checkpoint()
    return {"status": "imported_unverified", "dataset_count": len(state)}


def verify_data(config, path):
    require(config, ["ARIZE_API_KEY", "ARIZE_SPACE_ID"])
    manifest = load(path)
    validate_manifest_sources(manifest)
    client = ax_client(config)
    differences = []
    totals = {
        "datasets": 0,
        "versions": 0,
        "examples": 0,
        "experiments": 0,
        "runs": 0,
        "evaluations": 0,
    }
    source_dataset_ids = {source["id"] for source in manifest["datasets"]}
    state_dataset_ids = set(manifest["state"])
    for source_id in sorted(source_dataset_ids - state_dataset_ids):
        differences.append(f"manifest missing dataset mapping {source_id}")
    for source_id in sorted(state_dataset_ids - source_dataset_ids):
        differences.append(f"manifest has unexpected dataset mapping {source_id}")
    destination_dataset_ids = [
        state.get("dataset_id")
        for state in manifest["state"].values()
        if state.get("dataset_id")
    ]
    if len(destination_dataset_ids) != len(set(destination_dataset_ids)):
        differences.append("manifest has duplicate destination dataset mappings")
    for source in manifest["datasets"]:
        state = manifest["state"].get(source["id"])
        if not state:
            differences.append(f"dataset {source['name']} was not imported")
            continue
        totals["datasets"] += 1
        latest_destination_examples = None
        source_version_ids = {version["id"] for version in source["versions"]}
        mapped_version_ids = set(state["version_ids"])
        if source_version_ids != mapped_version_ids:
            differences.append(
                f"dataset {source['name']} version mapping IDs differ"
            )
        destination_version_ids = list(state["version_ids"].values())
        if len(destination_version_ids) != len(set(destination_version_ids)):
            differences.append(
                f"dataset {source['name']} has duplicate destination version mappings"
            )
        for version in source["versions"]:
            destination_id = state["version_ids"].get(version["id"])
            if not destination_id:
                differences.append(
                    f"dataset {source['name']} missing version {version['id']}"
                )
                continue
            totals["versions"] += 1
            actual = destination_examples(client, state["dataset_id"], destination_id)
            if version["id"] == source["versions"][-1]["id"]:
                latest_destination_examples = actual
            expected_examples = unique_index(
                version["examples"],
                lambda example: example.get("source_global_id"),
                f"Dataset {source['name']} version {version['id']} examples",
            )
            expected = {key: ax_row(value) for key, value in expected_examples.items()}
            totals["examples"] += len(expected)
            if set(actual) != set(expected):
                differences.append(
                    f"dataset {source['name']} version {version['id']} example IDs differ"
                )
            for key in set(actual) & set(expected):
                props = actual[key].additional_properties
                if any(
                    props.get(field) != value for field, value in expected[key].items()
                ):
                    differences.append(
                        f"dataset {source['name']} example {key} fields differ"
                    )
        by_source = unique_index(
            source["experiments"],
            lambda experiment: experiment.get("id"),
            f"Dataset {source['name']} experiments",
        )
        mapped = unique_index(
            state["experiments"],
            lambda mapping: mapping.get("source_id"),
            f"Dataset {source['name']} experiment mappings",
        )
        destination_experiment_ids = [
            mapping.get("id") for mapping in state["experiments"]
        ]
        if any(not value for value in destination_experiment_ids):
            raise DataMigrationError(
                f"Dataset {source['name']} experiment mapping has a missing destination identity."
            )
        if len(destination_experiment_ids) != len(set(destination_experiment_ids)):
            differences.append(
                f"dataset {source['name']} has duplicate destination experiment mappings"
            )
        missing_mappings = sorted(set(by_source) - set(mapped))
        extra_mappings = sorted(set(mapped) - set(by_source))
        for source_id in missing_mappings:
            differences.append(
                f"dataset {source['name']} missing experiment mapping {source_id}"
            )
        for source_id in extra_mappings:
            differences.append(
                f"dataset {source['name']} has unexpected experiment mapping {source_id}"
            )
        for mapping in state["experiments"]:
            expected = by_source.get(mapping["source_id"])
            if expected is None:
                continue
            actual = client.experiments.list_runs(
                experiment=mapping["id"], dataset=state["dataset_id"], all=True
            ).experiment_runs
            totals["experiments"] += 1
            totals["runs"] += len(expected["task_runs"])
            totals["evaluations"] += len(expected["evaluation_runs"])
            expected_runs = unique_index(
                expected["task_runs"],
                lambda run: run.get("id"),
                f"Experiment {expected['name']} task runs",
            )
            actual_runs = unique_index(
                actual,
                lambda run: run.additional_properties.get(
                    "phoenix_experiment_run_id"
                ),
                f"Experiment {expected['name']} AX runs",
            )
            if set(actual_runs) != set(expected_runs):
                differences.append(f"experiment {expected['name']} run IDs differ")
            expected_evals = defaultdict(dict)
            for result in expected["evaluation_runs"]:
                expected_evals[result["experiment_run_id"]][result["name"]] = result
            for source_run, run in actual_runs.items():
                props = run.additional_properties
                task_run = expected_runs.get(source_run)
                if task_run is None:
                    differences.append(
                        f"experiment {expected['name']} has unexpected run {source_run}"
                    )
                    continue
                if run.output != canonical(task_run.get("output")):
                    differences.append(
                        f"experiment {expected['name']} run {source_run} output differs"
                    )
                source_example_id = task_run.get("dataset_example_id")
                destination_example = (latest_destination_examples or {}).get(
                    source_example_id
                )
                if (
                    destination_example is None
                    or run.example_id != destination_example.id
                ):
                    differences.append(
                        f"experiment {expected['name']} run {source_run} example relationship differs"
                    )
                provenance = experiment_run_provenance(expected, task_run)
                if any(props.get(field) != value for field, value in provenance.items()):
                    differences.append(
                        f"experiment {expected['name']} run {source_run} provenance differs"
                    )
                for name, result in expected_evals[source_run].items():
                    value = result.get("result") or {}
                    if (
                        props.get(f"eval.{name}.score") != value.get("score")
                        or props.get(f"eval.{name}.label") != value.get("label")
                        or props.get(f"eval.{name}.explanation")
                        != value.get("explanation")
                        or props.get(f"eval.{name}.metadata.phoenix_migration")
                        != evaluation_provenance(result)
                    ):
                        differences.append(
                            f"experiment {expected['name']} run {source_run} evaluation {name} differs"
                        )
                expected_eval_fields = {
                    f"eval.{name}.{field}"
                    for name in expected_evals[source_run]
                    for field in (
                        "score",
                        "label",
                        "explanation",
                        "metadata.phoenix_migration",
                    )
                }
                actual_eval_fields = {
                    field for field in props if field.startswith("eval.")
                }
                if actual_eval_fields != expected_eval_fields:
                    differences.append(
                        f"experiment {expected['name']} run {source_run} evaluation fields differ"
                    )
    return {
        "status": "verified" if not differences else "different",
        **totals,
        "difference_count": len(differences),
        "differences": differences[:100],
    }


def parser():
    result = argparse.ArgumentParser()
    result.add_argument("command", choices=("export", "import", "verify"))
    result.add_argument("--env-file", type=Path)
    result.add_argument("--manifest", type=Path, required=True)
    result.add_argument("--dataset", action="append")
    result.add_argument("--prefix", default="")
    return result


def main():
    args = parser().parse_args()
    try:
        config = configuration(args.env_file)
        if args.command == "export":
            result = export_data(config, args.manifest, args.dataset)
        elif args.command == "import":
            result = import_data(config, args.manifest, args.prefix)
        else:
            result = verify_data(config, args.manifest)
        print(canonical(result))
        return (
            0
            if result["status"] in {"exported", "imported_unverified", "verified"}
            else 3
        )
    except Exception as error:  # noqa: BLE001 -- CLI converts dependency failures to JSON
        if isinstance(error, DataMigrationError):
            message = str(error)
        elif type(error).__name__ in {"AuthenticationError", "UnauthorizedException"}:
            message = (
                "AX authentication or permission check failed; check the API key, "
                "space access, and endpoint configuration."
            )
        else:
            message = (
                f"{type(error).__name__} during data migration; check credentials, "
                "permissions, endpoint configuration, and destination state."
            )
        print(canonical({"status": "error", "error": message}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
