"""Real cooperating processes cannot both commit the same config revision."""

import multiprocessing

import config_io
import pytest

pytestmark = pytest.mark.integration


def write_snapshot(path, ready, result, name):
    snapshot = config_io.load_config(path)
    snapshot[name] = True
    ready.wait(timeout=10)
    try:
        config_io.dump_config(path, snapshot)
        result.put("saved")
    except ValueError:
        result.put("conflict")


def test_simultaneous_writers_commit_only_one_revision(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{}\n")
    context = multiprocessing.get_context("fork")
    ready, result = context.Barrier(2), context.Queue()
    processes = [
        context.Process(target=write_snapshot, args=(path, ready, result, name))
        for name in ("one", "two")
    ]
    try:
        for process in processes:
            process.start()
        assert sorted(result.get(timeout=10) for _ in processes) == [
            "conflict",
            "saved",
        ]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        assert len(config_io.load_config(path)) == 1
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join()
