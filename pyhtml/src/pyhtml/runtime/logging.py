import asyncio
import contextvars
import io
import sys

# Context variable to hold the log callback for the current request/session
# Callback signature: async def callback(message: str)
log_callback_ctx = contextvars.ContextVar("log_callback_ctx", default=None)


class ContextAwareStdout:
    """
    Simulates stdout but intercepts writes to send to specific clients
    based on the current context.
    """

    def __init__(self, original_stdout, level: str = "info"):
        self.original_stdout = original_stdout
        self.level = level
        self.buffer = io.StringIO()

    def write(self, message: str):
        # Always write to original stdout
        self.original_stdout.write(message)

        # Check context for callback
        callback = log_callback_ctx.get()
        if callback:
            # Schedule the callback
            # Since write is sync, we must schedule async task
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(self._safe_callback(callback, message))
            except RuntimeError:
                # No running loop, can't stream
                pass

    def flush(self):
        self.original_stdout.flush()

    async def _safe_callback(self, callback, message):
        try:
            # Check if callback accepts level argument
            import inspect

            sig = inspect.signature(callback)
            if "level" in sig.parameters:
                await callback(message, level=self.level)
            else:
                await callback(message)
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self.original_stdout, name)


# Global installation
_installed = False


def install_logging_interceptor():
    global _installed
    if not _installed:
        sys.stdout = ContextAwareStdout(sys.stdout, level="info")
        # Handle stderr too? Usually yes for errors.
        sys.stderr = ContextAwareStdout(sys.stderr, level="error")
        _installed = True
