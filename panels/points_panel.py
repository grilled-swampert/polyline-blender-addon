class POLYLINE_PT_points_panel(bpy.types.Panel):
    """Points detail panel"""
    bl_label = "Point Details"
    bl_idname = "POLYLINE_PT_points_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Polyline'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return context.scene.show_points_panel and context.scene.active_polyline_key >= 0
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        key = scene.active_polyline_key
        
        polyline = global_storage.get_list(key)
        if not polyline:
            layout.label(text="Invalid polyline")
            return
        
        # Header
        box = layout.box()
        box.label(text=f"Polyline_{key} ({polyline.size} points)", icon='CURVE_BEZCIRCLE')
        
        # Points list
        idx = 0
        for node in polyline:
            if node.obj:
                box = layout.box()
                
                # Point header with index
                row = box.row()
                row.label(text=f"Point [{idx}]", icon='LAYER_ACTIVE')
                row.operator("polyline.delete_point", text="", icon='X').point_name = node.obj.name
                
                # Location with labels
                col = box.column(align=True)
                split = col.split(factor=0.15, align=True)
                split.label(text="X:")
                row = split.row()
                row.prop(node.obj, "location", index=0, text="")
                row.operator("polyline.mark_modified", text="", icon='FILE_TICK')
                
                split = col.split(factor=0.15, align=True)
                split.label(text="Y:")
                row = split.row()
                row.prop(node.obj, "location", index=1, text="")
                row.operator("polyline.mark_modified", text="", icon='FILE_TICK')
                
                split = col.split(factor=0.15, align=True)
                split.label(text="Z:")
                row = split.row()
                row.prop(node.obj, "location", index=2, text="")
                row.operator("polyline.mark_modified", text="", icon='FILE_TICK')
                
                # Show coordinates as text
                loc = node.obj.location
                coord_label = f"({loc.x:.3f}, {loc.y:.3f}, {loc.z:.3f})"
                if node.is_endpoint:
                    box.label(text=coord_label + " [ENDPOINT]", icon='MESH_DATA')
                else:
                    box.label(text=coord_label, icon='EMPTY_AXIS')
                
                idx += 1
