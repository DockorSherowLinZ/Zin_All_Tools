# Smart Info Panel

3D floating info panel that displays AIF metadata for selected equipment in the viewport.

## Features

- **3D Floating Panel**: Displays metadata as a panel hovering above selected equipment in 3D space
- **AIF Metadata**: Reads `aif:core:*` and `aif:spec:*` attributes from USD prims
- **Smart Measure Dimensions**: Shows equipment bounding box dimensions (X, Y, Z) in cm
- **Scale Control**: Adjustable panel size via slider
- **Dual Toggle**: Toggle via Viewport toolbar button AND Zin Tools Box panel (synchronized)
- **Camera-Facing**: Panel always faces the camera for optimal readability

## Usage

1. Enable the extension in Extension Manager
2. Click the toggle button to activate info panel detection
3. Select any equipment in the 3D scene
4. A floating panel will appear above the selected equipment showing its metadata
5. Use the scale slider to adjust panel size
6. Deselect to hide the panel

## Integration

This extension integrates with the Zin Tools Box as a tab, providing a unified interface
alongside other Smart* tools (Measure, Align, Reference, etc.)
