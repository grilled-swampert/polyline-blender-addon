# ========================== OPERATORS ==========================

class POLYLINE_OT_generate_points(bpy.types.Operator):
    """Generate interpolation points along a selected edge"""
    bl_idname = "polyline.generate_points"
    bl_label = "Generate Points"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        # Get selected edge
        bm = bmesh.from_edit_mesh(obj.data)
        selected_edges = [e for e in bm.edges if e.select]
        
        if len(selected_edges) != 1:
            self.report({'ERROR'}, "Please select exactly one edge")
            return {'CANCELLED'}
        
        edge = selected_edges[0]
        v1 = obj.matrix_world @ edge.verts[0].co
        v2 = obj.matrix_world @ edge.verts[1].co
        
        # Store vertex indices
        v1_idx = edge.verts[0].index
        v2_idx = edge.verts[1].index
        
        # Create new polyline
        key = global_storage.create_list(
            curve_type=scene.polyline_curve_type,
            rotation=scene.polyline_rotation
        )
        
        # Store edge info and mesh reference in metadata
        metadata = global_storage.get_metadata(key)
        metadata['edge_start'] = v1.copy()
        metadata['edge_end'] = v2.copy()
        metadata['source_mesh'] = obj
        metadata['vertex_indices'] = [v1_idx, v2_idx]
        
        num_points = scene.polyline_num_points
        
        # Generate points based on curve type
        curve_type = scene.polyline_curve_type
        rotation = scene.polyline_rotation
        
        if curve_type == 'ARC':
            points = generate_arc_points(v1, v2, num_points, rotation)
        elif curve_type == 'SPLINE':
            points = generate_spline_points(v1, v2, num_points, rotation)
        elif curve_type == 'HELIX':
            points = generate_helix_points(v1, v2, num_points, rotation)
        else:  # LINEAR
            points = generate_linear_points(v1, v2, num_points)
        
        # Check collision detection and create objects
        collision_count = 0
        for i, point in enumerate(points):
            if scene.polyline_collision_detection and check_collision(point, context, scene.polyline_collision_threshold):
                collision_count += 1
                continue
            
            # Determine if this is an endpoint
            is_endpoint = (i == 0 or i == len(points) - 1)
            
            # Create empty object with better visualization
            empty = bpy.data.objects.new(f"PL{key}_P{i}", None)
            empty.location = point
            empty.empty_display_size = 0.1 if is_endpoint else 0.08
            empty.empty_display_type = 'SPHERE'
            empty.show_name = scene.polyline_show_labels
            
            # Color endpoints differently
            if is_endpoint:
                empty.color = (1.0, 0.3, 0.3, 1.0)  # Red for endpoints
            else:
                empty.color = (0.3, 0.8, 1.0, 1.0)  # Blue for regular points
            
            context.collection.objects.link(empty)
            
            # Insert with endpoint flag
            node = global_storage.insert_into_list(key, point.copy(), empty, is_endpoint=is_endpoint)
            
            # Link to mesh vertex for endpoints
            if is_endpoint:
                node.linked_mesh = obj
                node.last_vertex_pos = point.copy()
                node.last_empty_pos = point.copy()
                if i == 0:
                    node.linked_vertex = v1_idx
                else:
                    node.linked_vertex = v2_idx
        
        # Update UI
        global_storage.update_polyline_list(context)
        scene.active_polyline_key = key
        
        # Enable sync handler if not already enabled
        global update_handler
        if update_handler is None:
            update_handler = bpy.app.timers.register(sync_endpoint_timer, persistent=True)
        
        if collision_count > 0:
            self.report({'WARNING'}, f"Generated polyline with {collision_count} collision(s) avoided")
        else:
            self.report({'INFO'}, f"Generated Polyline_{key} with {len(points)} points (endpoints linked)")
        
        return {'FINISHED'}


class POLYLINE_OT_rotate_polyline(bpy.types.Operator):
    """Rotate the polyline around its edge axis (regenerates curve)"""
    bl_idname = "polyline.rotate_polyline"
    bl_label = "Reset & Rotate"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        key = scene.active_polyline_key
        
        if key < 0:
            self.report({'ERROR'}, "No polyline selected")
            return {'CANCELLED'}
        
        polyline = global_storage.get_list(key)
        metadata = global_storage.get_metadata(key)
        
        if not polyline or not metadata.get('edge_start'):
            self.report({'ERROR'}, "Invalid polyline")
            return {'CANCELLED'}
        
        # Get current endpoint positions
        source_mesh = metadata.get('source_mesh')
        if source_mesh and source_mesh.name in bpy.data.objects:
            mesh_obj = bpy.data.objects[source_mesh.name]
            vertex_indices = metadata.get('vertex_indices', [None, None])
            
            if mesh_obj.mode == 'EDIT':
                bm = bmesh.from_edit_mesh(mesh_obj.data)
                bm.verts.ensure_lookup_table()
                
                if vertex_indices[0] is not None and vertex_indices[0] < len(bm.verts):
                    v1 = mesh_obj.matrix_world @ bm.verts[vertex_indices[0]].co
                    metadata['edge_start'] = v1.copy()
                else:
                    v1 = metadata['edge_start']
                
                if vertex_indices[1] is not None and vertex_indices[1] < len(bm.verts):
                    v2 = mesh_obj.matrix_world @ bm.verts[vertex_indices[1]].co
                    metadata['edge_end'] = v2.copy()
                else:
                    v2 = metadata['edge_end']
            else:
                if polyline.head and polyline.head.obj:
                    v1 = polyline.head.obj.location.copy()
                    metadata['edge_start'] = v1
                else:
                    v1 = metadata['edge_start']
                
                if polyline.tail and polyline.tail.obj:
                    v2 = polyline.tail.obj.location.copy()
                    metadata['edge_end'] = v2
                else:
                    v2 = metadata['edge_end']
        else:
            v1 = metadata['edge_start']
            v2 = metadata['edge_end']
        
        num_points = polyline.size - 1
        
        # Get rotation from the polyline list item
        for item in scene.polyline_list:
            if item.key == key:
                rotation = item.rotation
                break
        else:
            rotation = scene.polyline_rotation
        
        curve_type = metadata['curve_type']
        
        metadata['rotation'] = rotation
        metadata['is_modified'] = False  # Reset modification flag
        
        # Regenerate points with new rotation
        if curve_type == 'ARC':
            points = generate_arc_points(v1, v2, num_points, rotation)
        elif curve_type == 'SPLINE':
            points = generate_spline_points(v1, v2, num_points, rotation)
        elif curve_type == 'HELIX':
            points = generate_helix_points(v1, v2, num_points, rotation)
        else:
            self.report({'WARNING'}, "Cannot rotate linear polylines")
            return {'CANCELLED'}
        
        # Update existing objects and tracking positions
        idx = 0
        for node in polyline:
            if idx < len(points) and node.obj:
                new_pos = points[idx]
                node.obj.location = new_pos
                node.location = new_pos.copy()
                
                if node.is_endpoint:
                    node.last_empty_pos = new_pos.copy()
                    node.last_vertex_pos = new_pos.copy()
                    
                    if source_mesh and source_mesh.name in bpy.data.objects:
                        mesh_obj = bpy.data.objects[source_mesh.name]
                        if mesh_obj.mode == 'EDIT' and node.linked_vertex is not None:
                            bm = bmesh.from_edit_mesh(mesh_obj.data)
                            bm.verts.ensure_lookup_table()
                            if node.linked_vertex < len(bm.verts):
                                local_pos = mesh_obj.matrix_world.inverted() @ new_pos
                                bm.verts[node.linked_vertex].co = local_pos
                                bmesh.update_edit_mesh(mesh_obj.data)
            idx += 1
        
        # Update the list item
        for item in scene.polyline_list:
            if item.key == key:
                item.is_modified = False
                break
        
        # Force viewport update
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        self.report({'INFO'}, f"Reset and rotated Polyline_{key} to {rotation}°")
        return {'FINISHED'}


class POLYLINE_OT_merge_polylines(bpy.types.Operator):
    """Merge two polylines"""
    bl_idname = "polyline.merge_polylines"
    bl_label = "Merge Polylines"
    bl_options = {'REGISTER', 'UNDO'}
    
    target_key: bpy.props.IntProperty()
    
    def execute(self, context):
        scene = context.scene
        source_key = scene.active_polyline_key
        
        if source_key < 0:
            self.report({'ERROR'}, "No source polyline selected")
            return {'CANCELLED'}
        
        if source_key == self.target_key:
            self.report({'ERROR'}, "Cannot merge polyline with itself")
            return {'CANCELLED'}
        
        result = global_storage.merge_polylines(source_key, self.target_key)
        
        if result:
            global_storage.update_polyline_list(context)
            scene.active_polyline_key = result
            self.report({'INFO'}, f"Merged polylines into Polyline_{result}")
        else:
            self.report({'ERROR'}, "Failed to merge polylines")
            return {'CANCELLED'}
        
        return {'FINISHED'}


class POLYLINE_OT_draw_line(bpy.types.Operator):
    """Enable/disable polyline visualization"""
    bl_idname = "polyline.draw_line"
    bl_label = "Toggle Visualization"
    
    def execute(self, context):
        global draw_handler
        
        if draw_handler is None:
            draw_handler = bpy.types.SpaceView3D.draw_handler_add(
                draw_polylines, (context,), 'WINDOW', 'POST_VIEW'
            )
            context.scene.polyline_draw_enabled = True
            self.report({'INFO'}, "Visualization enabled")
        else:
            bpy.types.SpaceView3D.draw_handler_remove(draw_handler, 'WINDOW')
            draw_handler = None
            context.scene.polyline_draw_enabled = False
            self.report({'INFO'}, "Visualization disabled")
        
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}


class POLYLINE_OT_delete_line(bpy.types.Operator):
    """Delete the active polyline"""
    bl_idname = "polyline.delete_line"
    bl_label = "Delete Polyline"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        key = scene.active_polyline_key
        
        if key < 0:
            self.report({'ERROR'}, "No polyline selected")
            return {'CANCELLED'}
        
        global_storage.delete_polyline(key, context)
        scene.active_polyline_key = -1
        scene.show_points_panel = False
        
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        self.report({'INFO'}, f"Deleted Polyline_{key}")
        return {'FINISHED'}


class POLYLINE_OT_toggle_points(bpy.types.Operator):
    """Toggle points panel visibility"""
    bl_idname = "polyline.toggle_points"
    bl_label = "Toggle Points"
    
    def execute(self, context):
        scene = context.scene
        if scene.active_polyline_key >= 0:
            scene.show_points_panel = not scene.show_points_panel
        else:
            self.report({'WARNING'}, "Select a polyline first")
        return {'FINISHED'}


class POLYLINE_OT_delete_point(bpy.types.Operator):
    """Delete a specific point"""
    bl_idname = "polyline.delete_point"
    bl_label = "Delete"
    bl_options = {'REGISTER', 'UNDO'}
    
    point_name: bpy.props.StringProperty()
    
    def execute(self, context):
        scene = context.scene
        key = scene.active_polyline_key
        
        if key < 0:
            return {'CANCELLED'}
        
        polyline = global_storage.get_list(key)
        metadata = global_storage.get_metadata(key)
        
        if not polyline:
            return {'CANCELLED'}
        
        for node in polyline:
            if node.obj and node.obj.name == self.point_name:
                bpy.data.objects.remove(node.obj, do_unlink=True)
                polyline.delete_node(node)
                
                # Mark as modified
                metadata['is_modified'] = True
                for item in scene.polyline_list:
                    if item.key == key:
                        item.is_modified = True
                break
        
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}


class POLYLINE_OT_select_polyline(bpy.types.Operator):
    """Select a polyline as active"""
    bl_idname = "polyline.select_polyline"
    bl_label = "Select"
    
    key: bpy.props.IntProperty()
    
    def execute(self, context):
        context.scene.active_polyline_key = self.key
        return {'FINISHED'}


class POLYLINE_OT_toggle_labels(bpy.types.Operator):
    """Toggle point labels visibility"""
    bl_idname = "polyline.toggle_labels"
    bl_label = "Toggle Labels"
    
    def execute(self, context):
        scene = context.scene
        scene.polyline_show_labels = not scene.polyline_show_labels
        
        # Update all point objects
        for key in global_storage.polyline_storage:
            polyline = global_storage.get_list(key)
            for node in polyline:
                if node.obj:
                    node.obj.show_name = scene.polyline_show_labels
        
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}


class POLYLINE_OT_mark_modified(bpy.types.Operator):
    """Mark polyline as manually modified when point location changes"""
    bl_idname = "polyline.mark_modified"
    bl_label = "Mark Modified"
    
    def execute(self, context):
        scene = context.scene
        key = scene.active_polyline_key
        
        if key < 0:
            return {'CANCELLED'}
        
        metadata = global_storage.get_metadata(key)
        if metadata:
            metadata['is_modified'] = True
            
            # Update UI
            for item in scene.polyline_list:
                if item.key == key:
                    item.is_modified = True
                    break
        
        return {'FINISHED'}

