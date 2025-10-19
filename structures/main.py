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

