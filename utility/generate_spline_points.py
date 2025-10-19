from mathutils import Vector, Matrix
import math

def generate_spline_points(v1, v2, num_points, rotation=0.0):
    """Generate points along a cubic spline"""
    direction = (v2 - v1).normalized()
    distance = (v2 - v1).length
    
    # Create control points for cubic spline
    if abs(direction.z) < 0.9:
        up = Vector((0, 0, 1))
    else:
        up = Vector((1, 0, 0))
    
    perp = direction.cross(up).normalized()
    rot_matrix = Matrix.Rotation(math.radians(rotation), 4, direction)
    perp = (rot_matrix @ perp.to_4d()).to_3d()
    
    ctrl1 = v1 + direction * distance * 0.33 + perp * distance * 0.3
    ctrl2 = v1 + direction * distance * 0.67 + perp * distance * 0.3
    
    points = []
    for i in range(num_points + 1):
        t = i / num_points
        # Cubic Bezier formula
        point = (1-t)**3 * v1 + 3*(1-t)**2*t * ctrl1 + 3*(1-t)*t**2 * ctrl2 + t**3 * v2
        points.append(point)
    
    return points

