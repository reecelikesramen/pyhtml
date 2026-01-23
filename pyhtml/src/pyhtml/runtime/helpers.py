import inspect

async def ensure_async_iterator(iterable):
    """
    Ensure an iterable is an async iterator.
    Handles both sync iterables (list, etc.) and async iterables.
    """
    if hasattr(iterable, '__aiter__'):
        async for item in iterable:
            yield item
    elif hasattr(iterable, '__iter__'):
        for item in iterable:
            yield item
    else:
        # Fallback or error?
        # Maybe it's a generator?
        # If it's not iterable at all, standard for loop raises TypeError.
        # We should probably let it raise, or wrapping non-iterable?
        for item in iterable: # This will raise if not iterable
             yield item
