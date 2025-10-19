def generate_helix_points(v1, v2, num_points, rotation=0.0):
    """Generate points along a helical path"""
    direction = (v2 - v1).normalized()
    distance = (v2 - v1).length
    
    if abs(direction.z) < 0.9:
        up = Vector((0, 0, 1))
    else:
        up = Vector((1, 0, 0))
    
    perp1 = direction.cross(up).normalized()
    rot_matrix = Matrix.Rotation(math.radians(rotation), 4, direction)
    perp1 = (rot_matrix @ perp1.to_4d()).to_3d()
    perp2 = direction.cross(perp1).normalized()
    
    radius = distance * 0.15
    points = []
    
    for i in range(num_points + 1):
        t = i / num_points
        angle = t * math.pi * 2  # One full rotation
        
        radial_offset = perp1 * (radius * math.cos(angle)) + perp2 * (radius * math.sin(angle))
        point = v1 + direction * (distance * t) + radial_offset
        points.append(point)
    
    return points

