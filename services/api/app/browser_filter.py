"""Conservative request filtering for browser evidence captures."""


def filter_request(route) -> None:
    if route.request.resource_type == "media":
        route.abort()
    else:
        route.continue_()
