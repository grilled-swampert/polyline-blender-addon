import bpy
import bmesh
from ..utility.global_storage import global_storage

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
