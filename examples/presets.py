"""
Example: Presets Showcase
Demonstrating all available presets.
"""
from canopy import CanopyRenderer
from canopy.effects.presets import list_presets, get_preset_description

renderer = CanopyRenderer(width=800, height=600)

print("Available Presets:")
print("-" * 40)

for preset_name in list_presets():
    description = get_preset_description(preset_name)
    print(f"\n{preset_name}:")
    print(f"  {description}")
    
    # Apply and render
    renderer.reset(seed=42)  # Reset with same seed for comparison
    renderer.apply_preset(preset_name)
    
    frame = renderer.render_frame()
    output_file = f"preset_{preset_name}.png"
    renderer.to_image(frame, output_file)
    print(f"  → Saved to {output_file}")

print("\n" + "=" * 40)
print("All presets rendered! Compare them side by side.")
