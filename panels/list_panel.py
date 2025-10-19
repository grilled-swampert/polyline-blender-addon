class POLYLINE_PT_list_panel(bpy.types.Panel):
    """Polyline list panel"""
    bl_label = "Polyline Library"
    bl_idname = "POLYLINE_PT_list_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Polyline'
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        if not scene.polyline_list:
            layout.label(text="No polylines created", icon='INFO')
            return
        
        for item in scene.polyline_list:
            box = layout.box()
            
            # Header row
            row = box.row(align=True)
            row.prop(item, "visible", text="", icon='HIDE_OFF' if item.visible else 'HIDE_ON')
            
            op = row.operator("polyline.select_polyline", text=item.name, emboss=False)
            op.key = item.key
            
            # Show modified indicator
            if item.is_modified:
                row.label(text="", icon='BRUSHES_ALL')
            
            # Show merge button for other polylines
            if scene.active_polyline_key >= 0 and scene.active_polyline_key != item.key:
                op = row.operator("polyline.merge_polylines", text="", icon='EXPERIMENTAL')
                op.target_key = item.key
            
            # Properties (when visible)
            if item.visible:
                split = box.split(factor=0.3)
                split.label(text="Color:")
                split.prop(item, "color", text="")
                
                split = box.split(factor=0.3)
                split.label(text="Width:")
                split.prop(item, "line_width", text="", slider=True)
                
                # Rotation control for non-linear curves
                metadata = global_storage.get_metadata(item.key)
                if metadata and metadata.get('curve_type') != 'LINEAR':
                    split = box.split(factor=0.3)
                    split.label(text="Rotation:")
                    col = split.column()
                    col.enabled = not item.is_modified
                    col.prop(item, "rotation", text="", slider=True)
                    
                    if item.is_modified:
                        box.label(text="⚠ Modified - rotation disabled", icon='ERROR')
                        if scene.active_polyline_key == item.key:
                            box.operator("polyline.rotate_polyline", icon='FILE_REFRESH')
