"""
Example: Basic Usage
The sacred ritual of rendering a single frame.
"""
from canopy import CanopyRenderer, Archive

# Create the renderer with a deterministic seed
# The same seed will always produce the same output
renderer = CanopyRenderer(width=1920, height=1080, seed=12345)

# Bind an archive for saving states
archive = Archive()
renderer.bind_archive(archive)

# Enable some effects
renderer.effects.enable("vignette")
renderer.effects.enable("bloom")
renderer.effects.enable("color_shift")

# Set effect parameters
renderer.effects.set_param("bloom", "threshold", 0.7)
renderer.effects.set_param("bloom", "intensity", 0.4)
renderer.effects.set_param("color_shift", "hue_shift", 0.1)

# Apply grid deformation
renderer.grid.add_turbulence(octaves=4, intensity=0.03)
renderer.grid.add_kaleidoscope(segments=6)

# Render!
frame = renderer.render_frame()

# Save as image
renderer.to_image(frame, "output.png")

# Save to archive for later
entry_id = renderer.save_to_archive(
    name="First Vision",
    metadata={"description": "My first canopy render"}
)

print(f"Saved as entry #{entry_id}")
print(f"Seed: {renderer.rng.seed}")

# Later, we can resurrect this exact state:
renderer.load_from_archive(entry_id)

# And render again - it will be identical!
same_frame = renderer.render_frame()
renderer.to_image(same_frame, "output_again.png")
