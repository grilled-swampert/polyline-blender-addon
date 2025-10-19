# Blender Polyline Add-on

A simple Blender add-on for generating and managing polylines (connected lines) in 3D space.
Created as a part of Summer Fellowship with FOSSEE, IIT Bombay (2024).

## Installation

1. Download the add-on folder
2. Open Blender → Edit → Preferences → Add-ons
3. Click "Install" and select the add-on zip file
4. Enable "Polyline Manager" checkbox

## Usage

1. Open the **3D Viewport**
2. Press `N` to open the sidebar
3. Find the **Polyline** tab
4. Click "Add Polyline" to create a new line
5. Configure settings (type, start/end points, etc.)
6. Click "Generate" to create the polyline

## Project Structure

```
polyline-addon/
├── __init__.py              # Entry point, registers everything
├── panels/
│   ├── main_panel.py        # Main control panel
│   ├── points_panel.py      # Points list view
│   └── list_panel.py        # Polyline list view
├── structure/
│   ├── main.py              # Data structure and storage definitions
├── operators/
│   └── main.py              # Button actions & logic
├── properties/
│   └── polylinelistitem.py  # Data model definitions
├── utility/
│   ├── generate_linear_points.py
│   ├── generate_arc_points.py
│   ├── generate_helix_points.py
│   ├── generate_spline_points.py
│   ├── check_collision.py
│   └── global_storage.py    # State manager
└── drawing/
    ├── draw_polylines.py    # Rendering logic
    └── sync_endpoint_timer.py
```

## Architecture

<img width="595" height="1101" alt="architecture" src="https://github.com/user-attachments/assets/92a34de2-c47d-4fa5-81ac-92f10ca1a1a1" />


