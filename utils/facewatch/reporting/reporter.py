import threading
from .server   import create_app
from .notifier import start_notifier


class Reporter:
    def __init__(self, db_path: str, port: int, report_times: str):
        self._db_path      = db_path
        self._port         = port
        self._report_times = report_times
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        flask_app = create_app(self._db_path)

        def _serve():
            import logging
            log = logging.getLogger("werkzeug")
            log.setLevel(logging.ERROR)
            flask_app.run(host="127.0.0.1", port=self._port, use_reloader=False)

        self._thread = threading.Thread(target=_serve, daemon=True)
        self._thread.start()
        start_notifier(self._port, self._report_times)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
