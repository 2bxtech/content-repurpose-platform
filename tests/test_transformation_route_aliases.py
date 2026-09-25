from app.api.routes.transformations import router


def _methods_for(path: str) -> set[str]:
    methods: set[str] = set()
    for route in router.routes:
        if getattr(route, "path", None) == path:
            methods.update(getattr(route, "methods", set()))
    return methods


def test_transformation_collection_accepts_both_url_forms():
    assert "POST" in _methods_for("")
    assert "POST" in _methods_for("/")
    assert "GET" in _methods_for("")
    assert "GET" in _methods_for("/")
