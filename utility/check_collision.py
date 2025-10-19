import bmesh

def check_collision(point, context, threshold=0.01):
    """Check if a point collides with any mesh objects"""
    depsgraph = context.evaluated_depsgraph_get()
    
    for obj in context.scene.objects:
        if obj.type != 'MESH' or not obj.visible_get():
            continue
        
        # Transform point to object's local space
        local_point = obj.matrix_world.inverted() @ point
        
        # Create a temporary bmesh
        bm = bmesh.new()
        bm.from_object(obj, depsgraph)
        bm.faces.ensure_lookup_table()
        
        # Check distance to each face
        for face in bm.faces:
            # Get face center and normal
            face_center = face.calc_center_median()
            distance = (local_point - face_center).length
            
            if distance < threshold:
                bm.free()
                return True
        
        bm.free()
    
    return False
