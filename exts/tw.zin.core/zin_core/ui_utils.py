import omni.ui as ui

# =============================================================================
# zin_ui_utils.py
# Zin All Tools — Centralized UI Utility Module
#
# Standardized UI styling and layout rules to strictly match the native 
# Omniverse Property Panel design guidelines.
# =============================================================================

# ─────────────────────────────────────────────
# Global Layout Constants
# ─────────────────────────────────────────────
ZIN_ROW_SPACING = 8       # Horizontal spacing between label and input widget
ZIN_V_SPACING = 4         # Vertical spacing between rows in a VStack
ZIN_LABEL_WIDTH_PCT = 35  # Property labels take exactly 35% of the panel width

# ─────────────────────────────────────────────
# Native Omniverse Style Dictionary
# ─────────────────────────────────────────────
ZIN_NATIVE_STYLE = {
    # ── Backgrounds & Frames ──────────────────
    "CollapsableFrame": {
        "background_color": 0x00000000,
        "color": 0xFFDDDDDD,
        "font_size": 16,
    },
    
    # ── Labels ──────────────────────────────
    "Label::PropertyLabel": {
        "color": 0xFFDDDDDD,
        "font_size": 14,
    },
    "Label::Description": {
        "color": 0xFFAAAAAA,
        "font_size": 13,
    },
    
    # ── Buttons ─────────────────────────────
    "Button": {
        "background_color": 0xFF343432,
        "border_radius": 4,
        "margin": 2,
    },
    "Button:hovered": {
        "background_color": 0xFF4A4A48,
    },
    "Button:pressed": {
        "background_color": 0xFF5A5A58,
    },
    
    # ── Buttons: Correct/Action ─────────────
    "Button.Correct": {
        "background_color": 0xFF2A5E2A,
        "border_radius": 4,
        "margin": 2,
    },
    "Button.Correct:hovered": {
        "background_color": 0xFF33703A,
    },
    "Button.Correct:pressed": {
        "background_color": 0xFF44AA44,
    },
    
    # ── Buttons: Error/Remove ───────────────
    "Button.Error": {
        "background_color": 0xFF5E2A2A,
        "border_radius": 4,
        "margin": 2,
    },
    "Button.Error:hovered": {
        "background_color": 0xFF703333,
    },
    "Button.Error:pressed": {
        "background_color": 0xFFAA4444,
    },
}

# ─────────────────────────────────────────────
# Standalone Button Styles (For dynamic overriding)
# ─────────────────────────────────────────────
STYLE_POSITIVE = { 
    "Button": { "background_color": 0xFF2A5E2A }, 
    "Button:hovered": { "background_color": 0xFF33703A }, 
    "Button:pressed": { "background_color": 0xFF1F471F } 
}

STYLE_NEGATIVE = { 
    "Button": { "background_color": 0xFF5E2A2A }, 
    "Button:hovered": { "background_color": 0xFF703333 }, 
    "Button:pressed": { "background_color": 0xFF471F1F } 
}

# ─────────────────────────────────────────────
# Standardized Row Builders
# ─────────────────────────────────────────────

def build_property_row(label_text, widget_builder_fn, tooltip=""):
    """
    Creates a standard property row matching the Omniverse property panel layout.
    
    Args:
        label_text (str): The text for the property label.
        widget_builder_fn (callable): A function that creates the right-side widget.
                                      It will be executed within the row's HStack context.
        tooltip (str): Optional tooltip for the label.
    """
    with ui.HStack(height=24, spacing=ZIN_ROW_SPACING):
        # 1. Left Label Column (Fixed 35% width)
        ui.Label(
            label_text, 
            name="PropertyLabel",
            width=ui.Percent(ZIN_LABEL_WIDTH_PCT), 
            tooltip=tooltip
        )
        
        # 2. Right Widget Column (Remaining space)
        # The widget_builder_fn is responsible for constructing the right-side elements
        # like ComboBox, StringField, CheckBox + Label, etc.
        widget_builder_fn()

def build_checkbox_row(label_text, checkbox_model, description_text="", tooltip=""):
    """
    Creates a standardized row containing a checkbox with its descriptive text,
    aligned to the right-side widget column.
    
    Args:
        label_text (str): The text for the left property label.
        checkbox_model (ui.SimpleBoolModel): The model for the checkbox.
        description_text (str): The text displayed right next to the checkbox.
        tooltip (str): Optional tooltip for the property label.
    """
    def _build_checkbox():
        with ui.HStack(spacing=ZIN_ROW_SPACING):
            cb = ui.CheckBox(width=20)
            cb.model = checkbox_model
            if description_text:
                ui.Label(description_text, name="Description")
                
    build_property_row(label_text, _build_checkbox, tooltip)

def build_button_row(label_text, button_text, clicked_fn, style_dict=None, tooltip=""):
    """
    Creates a standardized row with an empty left label and a button on the right.
    """
    def _build_button():
        ui.Button(
            button_text, 
            style=style_dict if style_dict else {},
            clicked_fn=clicked_fn, 
            tooltip=tooltip
        )
    
    build_property_row(label_text, _build_button)
