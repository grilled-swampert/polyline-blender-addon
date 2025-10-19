from ..utility.global_storage import global_storage
import bpy

class POLYLINE_PT_main_panel(bpy.types.Panel):
    """Main control panel"""
    bl_label = "Polyline Generator"
    bl_idname = "POLYLINE_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Polyline'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Generation settings
        box = layout.box()
        box.label(text="Generation Settings", icon='SETTINGS')
        box.prop(scene, "polyline_num_points")
        box.prop(scene, "polyline_curve_type")
        
        if scene.polyline_curve_type != 'LINEAR':
            box.prop(scene, "polyline_rotation", slider=True)
        
        # Collision detection
        col = box.column()
        col.prop(scene, "polyline_collision_detection")
        if scene.polyline_collision_detection:
            col.prop(scene, "polyline_collision_threshold")
        
        box.separator()
        box.operator("polyline.generate_points", icon='CURVE_PATH')
        
        # Visualization
        box = layout.box()
        box.label(text="Visualization", icon='HIDE_OFF')
        
        row = box.row(align=True)
        icon = 'HIDE_OFF' if scene.polyline_draw_enabled else 'HIDE_ON'
        row.operator("polyline.draw_line", icon=icon)
        row.operator("polyline.toggle_labels", icon='SORTALPHA')
        
        # Active polyline tools
        if scene.active_polyline_key >= 0:
            box = layout.box()
            box.label(text=f"Active: Polyline_{scene.active_polyline_key}", icon='CURVE_DATA')
            
            col = box.column(align=True)
            col.operator("polyline.toggle_points", icon='PROPERTIES')
            
            if scene.polyline_curve_type != 'LINEAR':
                col.operator("polyline.rotate_polyline", icon='FILE_REFRESH')
            
            col.operator("polyline.delete_line", icon='TRASH')
