from forge_mcp.popular import popular_servers, popularity_metadata


def test_popular_catalog_contains_ranked_top_100():
    records = popular_servers(100)
    assert len(records) == 100
    assert records[0]["rank"] == 1
    assert records[-1]["rank"] == 100
    assert all(records[index]["rank"] < records[index + 1]["rank"] for index in range(99))


def test_popular_metadata_has_snapshot_and_source():
    metadata = popularity_metadata()
    assert metadata["snapshot_date"] == "2026-11-03"
    assert metadata["source"].startswith("https://")


def test_popular_limit_is_bounded():
    try:
        popular_servers(101)
    except ValueError:
        pass
    else:
        raise AssertionError("popular catalogue limit was not enforced")
