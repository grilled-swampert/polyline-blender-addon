def draw_polylines(context):
    """Draw handler for visualizing polylines"""
    scene = context.scene
    
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    
    for item in scene.polyline_list:
        if not item.visible:
            continue
        
        polyline = global_storage.get_list(item.key)
        if not polyline or polyline.size < 2:
            continue
        
        vertices = []
        for node in polyline:
            if node.obj:
                vertices.append(node.obj.location)
        
        if len(vertices) < 2:
            continue
        
        coords = []
        for i in range(len(vertices) - 1):
            coords.append(vertices[i])
            coords.append(vertices[i + 1])
        
        batch = batch_for_shader(shader, 'LINES', {"pos": coords})
        
        shader.bind()
        shader.uniform_float("color", item.color)
        
        gpu.state.line_width_set(item.line_width)
        batch.draw(shader)
    
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')
