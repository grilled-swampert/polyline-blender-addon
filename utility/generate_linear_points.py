def generate_linear_points(v1, v2, num_points):
    """Generate points along a straight line"""
    points = []
    for i in range(num_points + 1):
        t = i / num_points
        points.append(v1.lerp(v2, t))
    return points
