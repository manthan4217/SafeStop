try:
    from flask_limiter import Limiter  # type: ignore # pyright: ignore[reportMissingImports]
    from flask_limiter.util import get_remote_address  # type: ignore # pyright: ignore[reportMissingImports]

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["500 per day", "100 per hour"],
        storage_uri="memory://"
    )
except ImportError:
    class DummyLimiter:  # type: ignore
        def init_app(self, app):
            app.extensions['limiter'] = self
        def limit(self, *args, **kwargs):
            def decorator(f):
                return f
            return decorator

    limiter = DummyLimiter()  # type: ignore

