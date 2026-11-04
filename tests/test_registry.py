from forge_mcp.registry import ServerRecord


def test_normalizes_official_registry_record():
    item = {
        "server": {
            "name": "io.github.example/demo",
            "description": "Demo server",
            "repository": {"url": "https://github.com/example/demo"},
            "packages": [{"registryType": "npm", "identifier": "@example/demo"}],
            "remotes": [],
        },
        "version": "1.2.3",
        "status": "active",
    }
    record = ServerRecord.from_api(item)
    assert record.name == "io.github.example/demo"
    assert record.version == "1.2.3"
    assert record.repository == "https://github.com/example/demo"
    assert record.packages[0]["identifier"] == "@example/demo"
