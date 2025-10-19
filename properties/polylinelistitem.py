class PolylineListItem(bpy.types.PropertyGroup):
    """Property group for polyline list items"""
    name: bpy.props.StringProperty(name="Polyline Name")
    key: bpy.props.IntProperty(name="Polyline Key")
    visible: bpy.props.BoolProperty(
        name="Visible", 
        default=True,
        update=lambda self, context: context.area.tag_redraw() if context.area else None
    )
    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        default=(0.2, 0.7, 1.0, 1.0),
        size=4,
        min=0.0,
        max=1.0
    )
    line_width: bpy.props.FloatProperty(name="Line Width", default=3.0, min=1.0, max=10.0)
    rotation: bpy.props.FloatProperty(
        name="Rotation",
        description="Rotation angle for this polyline",
        default=0.0,
        min=-180.0,
        max=180.0,
        step=500,
        precision=1,
        update=lambda self, context: update_polyline_rotation(self, context)
    )
    is_modified: bpy.props.BoolProperty(
        name="Modified",
        description="Whether points have been manually edited",
        default=False
    )


def update_polyline_rotation(self, context):
    """Update callback for per-polyline rotation"""
    key = self.key
    polyline = global_storage.get_list(key)
    metadata = global_storage.get_metadata(key)
    
    if not polyline or not metadata:
        return
    
    # Don't regenerate if manually modified
    if self.is_modified:
        return
    
    curve_type = metadata.get('curve_type', 'ARC')
    if curve_type == 'LINEAR':
        return
    
    # Get current endpoint positions
    source_mesh = metadata.get('source_mesh')
    if source_mesh and source_mesh.name in bpy.data.objects:
        mesh_obj = bpy.data.objects[source_mesh.name]
        
        if polyline.head and polyline.head.obj:
            v1 = polyline.head.obj.location.copy()
        else:
            v1 = metadata.get('edge_start')
        
        if polyline.tail and polyline.tail.obj:
            v2 = polyline.tail.obj.location.copy()
        else:
            v2 = metadata.get('edge_end')
    else:
        v1 = metadata.get('edge_start')
        v2 = metadata.get('edge_end')
    
    if not v1 or not v2:
        return
    
    num_points = polyline.size - 1
    rotation = self.rotation
    
    # Regenerate points
    if curve_type == 'ARC':
        points = generate_arc_points(v1, v2, num_points, rotation)
    elif curve_type == 'SPLINE':
        points = generate_spline_points(v1, v2, num_points, rotation)
    elif curve_type == 'HELIX':
        points = generate_helix_points(v1, v2, num_points, rotation)
    else:
        return
    
    # Update all points
    idx = 0
    for node in polyline:
        if idx < len(points) and node.obj:
            new_pos = points[idx]
            node.obj.location = new_pos
            node.location = new_pos.copy()
            
            if node.is_endpoint:
                node.last_empty_pos = new_pos.copy()
                node.last_vertex_pos = new_pos.copy()
        idx += 1
    
    # Update metadata
    metadata['rotation'] = rotation
    
    # Force viewport refresh
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()

