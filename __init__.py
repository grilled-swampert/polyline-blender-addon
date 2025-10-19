bl_info = {
    "name": "Polyline Manager",
    "author": "crisplettuce",
    "version": (2, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Polyline",
    "description": "Advanced polyline management with collision detection, rotation, and multiple curve types",
    "category": "3D View",
}

import bpy
import bmesh
import math
from mathutils import Vector, Matrix
import gpu
from gpu_extras.batch import batch_for_shader
from bpy_extras import view3d_utils

# Import from submodules
from .drawing.draw_polylines import draw_polylines
from drawing.sync_endpoint_timer import sync_endpoint_timer
from .operators.main import (
    POLYLINE_OT_generate_points,
    POLYLINE_OT_rotate_polyline,
    POLYLINE_OT_merge_polylines,
    POLYLINE_OT_draw_line,
    POLYLINE_OT_delete_line,
    POLYLINE_OT_toggle_points,
    POLYLINE_OT_delete_point,
    POLYLINE_OT_select_polyline,
    POLYLINE_OT_toggle_labels,
    POLYLINE_OT_mark_modified,
)
from .panels.main_panel import POLYLINE_PT_main_panel
from .panels.list_panel import POLYLINE_PT_list_panel
from .panels.points_panel import POLYLINE_PT_points_panel
from .properties.polylinelistitem import PolylineListItem, update_polyline_rotation
from .structures.main import Node, LinkedList, Storage
from .utility.check_collision import check_collision
from .utility.endpoint_positions import sync_endpoint_positions
from .utility.generate_arc_points import generate_arc_points
from .utility.generate_helix_points import generate_helix_points
from .utility.generate_spline_points import generate_spline_points
from .utility.generate_linear_points import generate_linear_points
from .utility.global_storage import global_storage

# ========================== REGISTRATION ==========================

classes = (
    PolylineListItem,
    POLYLINE_OT_generate_points,
    POLYLINE_OT_rotate_polyline,
    POLYLINE_OT_merge_polylines,
    POLYLINE_OT_draw_line,
    POLYLINE_OT_delete_line,
    POLYLINE_OT_toggle_points,
    POLYLINE_OT_delete_point,
    POLYLINE_OT_select_polyline,
    POLYLINE_OT_toggle_labels,
    POLYLINE_OT_mark_modified,
    POLYLINE_PT_main_panel,
    POLYLINE_PT_list_panel,
    POLYLINE_PT_points_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Generation properties
    bpy.types.Scene.polyline_num_points = bpy.props.IntProperty(
        name="Number of Points",
        description="Number of interpolation points to generate along the edge",
        default=10,
        min=2,
        max=200
    )
    
    bpy.types.Scene.polyline_curve_type = bpy.props.EnumProperty(
        name="Curve Type",
        description="Type of curve for point generation",
        items=[
            ('LINEAR', "Linear", "Straight line between vertices", 'IPO_LINEAR', 0),
            ('ARC', "Arc", "Semicircular arc between vertices", 'IPO_CIRC', 1),
            ('SPLINE', "Spline", "Cubic spline curve", 'IPO_BEZIER', 2),
            ('HELIX', "Helix", "Helical spiral path", 'FORCE_VORTEX', 3),
        ],
        default='ARC'
    )
    
    bpy.types.Scene.polyline_rotation = bpy.props.FloatProperty(
        name="Rotation",
        description="Rotate the polyline around the edge axis (degrees)",
        default=0.0,
        min=-180.0,
        max=180.0,
        step=500,
        precision=1
    )
    
    # Collision detection properties
    bpy.types.Scene.polyline_collision_detection = bpy.props.BoolProperty(
        name="Collision Detection",
        description="Avoid generating points that collide with mesh objects",
        default=False
    )
    
    bpy.types.Scene.polyline_collision_threshold = bpy.props.FloatProperty(
        name="Collision Threshold",
        description="Minimum distance from mesh surfaces",
        default=0.05,
        min=0.001,
        max=1.0,
        precision=3
    )
    
    # Visualization properties
    bpy.types.Scene.polyline_show_labels = bpy.props.BoolProperty(
        name="Show Labels",
        description="Display point labels in viewport",
        default=True
    )
    
    bpy.types.Scene.polyline_draw_enabled = bpy.props.BoolProperty(
        name="Visualization Enabled",
        default=False
    )
    
    # Storage properties
    bpy.types.Scene.polyline_list = bpy.props.CollectionProperty(type=PolylineListItem)
    bpy.types.Scene.active_polyline_key = bpy.props.IntProperty(default=-1)
    bpy.types.Scene.show_points_panel = bpy.props.BoolProperty(default=False)
    
    # Start the sync timer
    global update_handler
    if update_handler is None:
        update_handler = bpy.app.timers.register(sync_endpoint_timer, persistent=True)


def unregister():
    global draw_handler, update_handler
    
    # Remove draw handler if active
    if draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(draw_handler, 'WINDOW')
        draw_handler = None
    
    # Remove sync timer
    if update_handler is not None:
        if bpy.app.timers.is_registered(sync_endpoint_timer):
            bpy.app.timers.unregister(sync_endpoint_timer)
        update_handler = None
    
    # Clean up properties
    del bpy.types.Scene.polyline_num_points
    del bpy.types.Scene.polyline_curve_type
    del bpy.types.Scene.polyline_rotation
    del bpy.types.Scene.polyline_collision_detection
    del bpy.types.Scene.polyline_collision_threshold
    del bpy.types.Scene.polyline_show_labels
    del bpy.types.Scene.polyline_draw_enabled
    del bpy.types.Scene.polyline_list
    del bpy.types.Scene.active_polyline_key
    del bpy.types.Scene.show_points_panel
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
    