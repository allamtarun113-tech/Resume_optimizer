from scripts.export_openapi import OUTPUT, render


def test_frontend_openapi_spec_is_up_to_date() -> None:
    assert OUTPUT.read_text() == render(), (
        "API changed: run `uv run python -m scripts.export_openapi` in backend/ "
        "and `pnpm gen:api` in frontend/"
    )
