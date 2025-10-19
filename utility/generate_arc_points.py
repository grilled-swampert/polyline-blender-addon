def generate_arc_points(v1, v2, num_points, rotation=0.0):
    """Generate points along a semicircular arc"""
    center = (v1 + v2) / 2
    radius = (v2 - v1).length / 2
    direction = (v2 - v1).normalized()
    
    # Create perpendicular vector
    if abs(direction.z) < 0.9:
        up = Vector((0, 0, 1))
    else:
        up = Vector((1, 0, 0))
    
    perp = direction.cross(up).normalized()
    
    # Apply rotation around the edge axis
    rot_matrix = Matrix.Rotation(math.radians(rotation), 4, direction)
    perp = (rot_matrix @ perp.to_4d()).to_3d()
    
    points = [v1.copy()]
    
    for i in range(1, num_points):
        angle = math.pi * i / num_points
        offset = perp * (radius * math.sin(angle))
        forward = direction * (radius * (1 - math.cos(angle)))
        points.append(v1 + forward + offset)
    
    points.append(v2.copy())
    return points
