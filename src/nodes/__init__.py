from langgraph.types import interrupt as _interrupt


def interrupt(value):
    """Wrapper around LangGraph's interrupt() that normalizes the resume value to a string."""
    result = _interrupt(value)
    if isinstance(result, list):
        result = result[0]
    return result
