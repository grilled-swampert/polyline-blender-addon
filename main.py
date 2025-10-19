bl_info = {
    "name": "Advanced Polyline Manager",
    "author": "Your Name",
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

# ========================== DATA STRUCTURES ==========================

class Node:
    """Represents a single point in a polyline"""
    def __init__(self, location, obj=None, index=0):
        self.location = location
        self.obj = obj
        self.next = None
        self.prev = None
        self.index = index
        self.is_endpoint = False  # Flag for endpoint nodes
        self.linked_vertex = None  # Reference to mesh vertex
        self.linked_mesh = None  # Reference to mesh object
        self.last_vertex_pos = None  # Track last known vertex position
        self.last_empty_pos = None  # Track last known empty position


class LinkedList:
    """Doubly linked list to store polyline points"""
    def __init__(self):
        self.head = None
        self.tail = None
        self.size = 0
    
    def insert(self, location, obj=None, index=None, is_endpoint=False):
        """Insert a new node at the end of the list"""
        if index is None:
            index = self.size
        new_node = Node(location, obj, index)
        new_node.is_endpoint = is_endpoint
        
        if self.head is None:
            self.head = new_node
            self.tail = new_node
        else:
            self.tail.next = new_node
            new_node.prev = self.tail
            self.tail = new_node
        
        self.size += 1
        return new_node
    
    def delete_node(self, node):
        """Delete a specific node from the list"""
        if node.prev:
            node.prev.next = node.next
        else:
            self.head = node.next
        
        if node.next:
            node.next.prev = node.prev
        else:
            self.tail = node.prev
        
        self.size -= 1
    
    def get_all_locations(self):
        """Get all point locations as a list"""
        return [node.location.copy() for node in self]
    
    def __iter__(self):
        """Iterator for traversing the list"""
        current = self.head
        while current:
            yield current
            current = current.next


class Storage:
    """Main storage class for managing multiple polylines"""
    def __init__(self):
        self.polyline_storage = {}
        self.polyline_metadata = {}  # Store curve type, rotation, etc.
        self.next_key = 0
    
    def create_list(self, curve_type='ARC', rotation=0.0):
        """Create a new polyline and return its unique key"""
        key = self.next_key
        self.polyline_storage[key] = LinkedList()
        self.polyline_metadata[key] = {
            'curve_type': curve_type,
            'rotation': rotation,
            'edge_start': None,
            'edge_end': None,
            'source_mesh': None,  # Track source mesh
            'vertex_indices': [],  # Track vertex indices
            'is_modified': False  # Track if manually edited
        }
        self.next_key += 1
        return key
    
    def insert_into_list(self, key, location, obj=None, is_endpoint=False):
        """Insert a point into a specific polyline"""
        if key in self.polyline_storage:
            return self.polyline_storage[key].insert(location, obj, is_endpoint=is_endpoint)
        return None
    
    def get_list(self, key):
        """Retrieve a polyline by its key"""
        return self.polyline_storage.get(key)
    
    def get_metadata(self, key):
        """Get metadata for a polyline"""
        return self.polyline_metadata.get(key, {})
    
    def merge_polylines(self, key1, key2):
        """Merge two polylines into one"""
        if key1 not in self.polyline_storage or key2 not in self.polyline_storage:
            return None
        
        polyline1 = self.polyline_storage[key1]
        polyline2 = self.polyline_storage[key2]
        
        # Connect the tail of polyline1 to the head of polyline2
        if polyline1.tail and polyline2.head:
            polyline1.tail.next = polyline2.head
            polyline2.head.prev = polyline1.tail
            polyline1.tail = polyline2.tail
            polyline1.size += polyline2.size
        
        # Remove the second polyline
        del self.polyline_storage[key2]
        del self.polyline_metadata[key2]
        
        return key1
    
    def delete_polyline(self, key, context):
        """Delete an entire polyline and clean up resources"""
        if key in self.polyline_storage:
            polyline = self.polyline_storage[key]
            
            # Remove all Blender objects
            for node in polyline:
                if node.obj and node.obj.name in bpy.data.objects:
                    bpy.data.objects.remove(node.obj, do_unlink=True)
            
            # Remove from storage
            del self.polyline_storage[key]
            if key in self.polyline_metadata:
                del self.polyline_metadata[key]
            
            # Update UI
            self.update_polyline_list(context)
    
    def update_polyline_list(self, context):
        """Update the UI polyline list"""
        scene = context.scene
        scene.polyline_list.clear()
        
        for key in self.polyline_storage.keys():
            item = scene.polyline_list.add()
            item.name = f"Polyline_{key}"
            item.key = key
            item.visible = True
            
            # Set rotation from metadata
            metadata = self.polyline_metadata.get(key, {})
            item.rotation = metadata.get('rotation', 0.0)
            item.is_modified = metadata.get('is_modified', False)


# Global storage instance
global_storage = Storage()
draw_handler = None
update_handler = None  # Handler for syncing endpoints


# ========================== UTILITY FUNCTIONS ==========================

def sync_endpoint_positions():
    """Sync positions between endpoint empties and mesh vertices"""
    for key in global_storage.polyline_storage:
        polyline = global_storage.get_list(key)
        metadata = global_storage.get_metadata(key)
        
        if not polyline:
            continue
        
        source_mesh = metadata.get('source_mesh')
        if not source_mesh or source_mesh.name not in bpy.data.objects:
            continue
        
        mesh_obj = bpy.data.objects[source_mesh.name]
        
        # Get vertex positions in world space
        if mesh_obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(mesh_obj.data)
            bm.verts.ensure_lookup_table()
            
            # Check first node (start endpoint)
            if polyline.head and polyline.head.is_endpoint and polyline.head.obj:
                v_idx = metadata.get('vertex_indices', [None, None])[0]
                if v_idx is not None and v_idx < len(bm.verts):
                    vert_world_pos = mesh_obj.matrix_world @ bm.verts[v_idx].co
                    empty_pos = polyline.head.obj.location
                    
                    # Initialize tracking if needed
                    if polyline.head.last_vertex_pos is None:
                        polyline.head.last_vertex_pos = vert_world_pos.copy()
                        polyline.head.last_empty_pos = empty_pos.copy()
                    
                    # Check what moved
                    vertex_moved = (vert_world_pos - polyline.head.last_vertex_pos).length > 0.0001
                    empty_moved = (empty_pos - polyline.head.last_empty_pos).length > 0.0001
                    
                    if vertex_moved and not empty_moved:
                        # Vertex moved, update empty
                        polyline.head.obj.location = vert_world_pos
                        polyline.head.location = vert_world_pos.copy()
                        polyline.head.last_vertex_pos = vert_world_pos.copy()
                        polyline.head.last_empty_pos = vert_world_pos.copy()
                    elif empty_moved and not vertex_moved:
                        # Empty moved, update vertex
                        local_pos = mesh_obj.matrix_world.inverted() @ empty_pos
                        bm.verts[v_idx].co = local_pos
                        bmesh.update_edit_mesh(mesh_obj.data)
                        polyline.head.last_vertex_pos = empty_pos.copy()
                        polyline.head.last_empty_pos = empty_pos.copy()
                    elif vertex_moved and empty_moved:
                        # Both moved - prefer empty movement (user interaction)
                        local_pos = mesh_obj.matrix_world.inverted() @ empty_pos
                        bm.verts[v_idx].co = local_pos
                        bmesh.update_edit_mesh(mesh_obj.data)
                        polyline.head.last_vertex_pos = empty_pos.copy()
                        polyline.head.last_empty_pos = empty_pos.copy()
            
            # Check last node (end endpoint)
            if polyline.tail and polyline.tail.is_endpoint and polyline.tail.obj:
                v_idx = metadata.get('vertex_indices', [None, None])[1]
                if v_idx is not None and v_idx < len(bm.verts):
                    vert_world_pos = mesh_obj.matrix_world @ bm.verts[v_idx].co
                    empty_pos = polyline.tail.obj.location
                    
                    # Initialize tracking if needed
                    if polyline.tail.last_vertex_pos is None:
                        polyline.tail.last_vertex_pos = vert_world_pos.copy()
                        polyline.tail.last_empty_pos = empty_pos.copy()
                    
                    # Check what moved
                    vertex_moved = (vert_world_pos - polyline.tail.last_vertex_pos).length > 0.0001
                    empty_moved = (empty_pos - polyline.tail.last_empty_pos).length > 0.0001
                    
                    if vertex_moved and not empty_moved:
                        # Vertex moved, update empty
                        polyline.tail.obj.location = vert_world_pos
                        polyline.tail.location = vert_world_pos.copy()
                        polyline.tail.last_vertex_pos = vert_world_pos.copy()
                        polyline.tail.last_empty_pos = vert_world_pos.copy()
                    elif empty_moved and not vertex_moved:
                        # Empty moved, update vertex
                        local_pos = mesh_obj.matrix_world.inverted() @ empty_pos
                        bm.verts[v_idx].co = local_pos
                        bmesh.update_edit_mesh(mesh_obj.data)
                        polyline.tail.last_vertex_pos = empty_pos.copy()
                        polyline.tail.last_empty_pos = empty_pos.copy()
                    elif vertex_moved and empty_moved:
                        # Both moved - prefer empty movement (user interaction)
                        local_pos = mesh_obj.matrix_world.inverted() @ empty_pos
                        bm.verts[v_idx].co = local_pos
                        bmesh.update_edit_mesh(mesh_obj.data)
                        polyline.tail.last_vertex_pos = empty_pos.copy()
                        polyline.tail.last_empty_pos = empty_pos.copy()
        else:
            # Object mode - only sync from vertex to empty (no edit mode available)
            vertex_indices = metadata.get('vertex_indices', [None, None])
            
            if polyline.head and polyline.head.is_endpoint and polyline.head.obj and vertex_indices[0] is not None:
                v_idx = vertex_indices[0]
                if v_idx < len(mesh_obj.data.vertices):
                    vert_world_pos = mesh_obj.matrix_world @ mesh_obj.data.vertices[v_idx].co
                    empty_pos = polyline.head.obj.location
                    
                    # Initialize tracking
                    if polyline.head.last_vertex_pos is None:
                        polyline.head.last_vertex_pos = vert_world_pos.copy()
                        polyline.head.last_empty_pos = empty_pos.copy()
                    
                    # In object mode, allow free movement of empties
                    # Only update tracking positions
                    polyline.head.last_vertex_pos = vert_world_pos.copy()
                    polyline.head.last_empty_pos = empty_pos.copy()
            
            if polyline.tail and polyline.tail.is_endpoint and polyline.tail.obj and vertex_indices[1] is not None:
                v_idx = vertex_indices[1]
                if v_idx < len(mesh_obj.data.vertices):
                    vert_world_pos = mesh_obj.matrix_world @ mesh_obj.data.vertices[v_idx].co
                    empty_pos = polyline.tail.obj.location
                    
                    # Initialize tracking
                    if polyline.tail.last_vertex_pos is None:
                        polyline.tail.last_vertex_pos = vert_world_pos.copy()
                        polyline.tail.last_empty_pos = empty_pos.copy()
                    
                    # In object mode, allow free movement of empties
                    # Only update tracking positions
                    polyline.tail.last_vertex_pos = vert_world_pos.copy()
                    polyline.tail.last_empty_pos = empty_pos.copy()


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


def generate_arc_points(v1, v2, num_points, rotation=0.0):
    """Generate points along a semicircular arc"""
    center = (v1 + v2) / 2
    radius = (v2 - v1).length / 2
    direction = (v2 - v1).normalized()
    
    # Create perpendicular vector
    if abs(direction.z) < 0.9:
        up = Vector((0, 0, 1))
    else:
        up = Vector((1, 0, 0))
    
    perp = direction.cross(up).normalized()
    
    # Apply rotation around the edge axis
    rot_matrix = Matrix.Rotation(math.radians(rotation), 4, direction)
    perp = (rot_matrix @ perp.to_4d()).to_3d()
    
    points = [v1.copy()]
    
    for i in range(1, num_points):
        angle = math.pi * i / num_points
        offset = perp * (radius * math.sin(angle))
        forward = direction * (radius * (1 - math.cos(angle)))
        points.append(v1 + forward + offset)
    
    points.append(v2.copy())
    return points


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


def generate_linear_points(v1, v2, num_points):
    """Generate points along a straight line"""
    points = []
    for i in range(num_points + 1):
        t = i / num_points
        points.append(v1.lerp(v2, t))
    return points


# ========================== PROPERTIES ==========================

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


# ========================== DRAWING ==========================

def sync_endpoint_timer():
    """Timer function to sync endpoints continuously"""
    try:
        sync_endpoint_positions()
    except:
        pass
    return 0.1  # Run every 0.1 seconds


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


# ========================== UI PANELS ==========================

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