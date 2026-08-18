from modules.app_runtime import ResourceArbiter, RuntimeStateStore, RuntimeStatus, ni_resource


def test_runtime_store_tracks_status_and_detail():
    runtime = RuntimeStateStore()
    runtime.set("daq", RuntimeStatus.WARNING, "busy")

    assert runtime.get("daq").status == RuntimeStatus.WARNING
    assert runtime.get("daq").detail == "busy"
    assert "scan" in runtime.snapshot()


def test_resource_arbiter_blocks_only_matching_ni_subsystem():
    resources = ResourceArbiter()

    assert resources.acquire("daq", [ni_resource("Dev3", "ai")])[0] is True
    assert resources.acquire("ao", [ni_resource("Dev3/ao0", "ao")])[0] is True

    acquired, detail = resources.acquire("force", [ni_resource("Dev3", "ai")])
    assert acquired is False
    assert "in use by daq" in detail

    resources.release("daq")
    assert resources.acquire("force", [ni_resource("Dev3", "ai")])[0] is True
