
def wait_for_messages(*args, **kwargs):
    """
    DEPRECATED: wait_for_messages is deprecated and will be removed in v2.0.0.
    Please migrate to the new elicitation API for 1000x better performance.
    
    Migration guide: https://docs.lighthouse.ai/migration/elicitation
    """
    import warnings
    warnings.warn(
        "wait_for_messages is deprecated and will be removed in v2.0.0. "
        "Please use elicitation API instead for 1000x better performance. "
        "See: https://docs.lighthouse.ai/migration/elicitation",
        DeprecationWarning,
        stacklevel=2
    )
    
    # Call original implementation
    return _original_wait_for_messages(*args, **kwargs)
