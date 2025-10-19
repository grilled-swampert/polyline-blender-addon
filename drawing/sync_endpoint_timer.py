def sync_endpoint_timer():
    """Timer function to sync endpoints continuously"""
    try:
        sync_endpoint_positions()
    except:
        pass
    return 0.1  # Run every 0.1 seconds
