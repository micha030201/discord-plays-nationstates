import functools


def call_once(func):
    called_already = False

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        nonlocal called_already
        if not called_already:
            called_already = True
            return await func(*args, **kwargs)
    return wrapper
