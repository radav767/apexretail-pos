"""Enumerate registered dependency guards; this is review input, not acceptance.

Run from a clean environment with the deliberately unreachable synthetic URL.
No DB access, ASGI lifespan, provider calls or request dispatch is performed.
"""
import csv
import inspect
import json
import os
from pathlib import Path
import sys

from sqlalchemy.engine import make_url


def main():
    url = make_url(os.environ.get('DATABASE_URL', ''))
    if (os.environ.get('APP_ENV') != 'test' or url.host != '127.0.0.1'
            or url.port != 1 or url.database != 'phase11_unreachable'):
        raise RuntimeError('Use APP_ENV=test and the explicit unreachable Phase 11 test URL')
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from app.main import app
    from fastapi.routing import APIRoute

    def dependencies(node):
        for child in node.dependencies:
            call = child.call
            name = getattr(call, '__module__', '') + '.' + getattr(call, '__qualname__', type(call).__name__)
            # Only capture the static permission name, never arbitrary closure data.
            if inspect.isfunction(call) and call.__closure__:
                closed = dict(zip(call.__code__.co_freevars, call.__closure__))
                if 'permission_key' in closed:
                    name += '[' + str(closed['permission_key'].cell_contents) + ']'
            yield name
            yield from dependencies(child)

    routes = []
    for route in app.routes:
        # FastAPI 0.139 keeps included routes as effective contexts. The
        # fallback supports ordinary APIRoute entries without copying prefixes.
        if hasattr(route, 'effective_route_contexts'):
            routes.extend(route.effective_route_contexts())
        elif isinstance(route, APIRoute):
            routes.append(route)
    rows = []
    for route in routes:
        if not route.include_in_schema:
            continue
        deps = sorted(set(dependencies(route.dependant)))
        source = Path(inspect.getsourcefile(route.endpoint)).relative_to(root)
        line = inspect.getsourcelines(route.endpoint)[1]
        for method in sorted(route.methods):
            rows.append({'method': method, 'path': route.path_format,
                         'source': f'backend/{source}:{line}',
                         'business_auth': 'required' if 'app.auth.dependencies.get_auth_actor' in deps
                         else 'optional' if 'app.auth.dependencies.get_optional_auth_actor' in deps else 'not_visible',
                         'billable_dependency': ';'.join(d for d in deps if 'require_billable_' in d),
                         'dependencies': ';'.join(deps),
                         'review': 'service_and_replay_review_required'})
    expected = {(method.upper(), path) for path, methods in app.openapi()['paths'].items()
                for method in methods if method in {'get', 'post', 'put', 'patch', 'delete', 'head', 'options'}}
    actual = {(row['method'], row['path']) for row in rows}
    if actual != expected or len(actual) != len(rows):
        raise RuntimeError('Registered route inventory does not match OpenAPI operations')
    rows.sort(key=lambda row: (row['path'], row['method']))
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    mutating = [r for r in rows if r['method'] not in {'GET', 'HEAD', 'OPTIONS'}]
    print(json.dumps({'operations': len(rows), 'mutating': len(mutating),
                      'mutating_with_visible_billable_dependency': sum(bool(r['billable_dependency']) for r in mutating),
                      'scope': 'dependency inventory only; service authorization and subscription enforcement require review'}), file=sys.stderr)


if __name__ == '__main__':
    main()
