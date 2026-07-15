"""
Example: Animation Rendering
Creating time-based visual sequences.
"""
from canopy import CanopyRenderer
import numpy as np

renderer = CanopyRenderer(width=1280, height=720, seed=42)

# Enable effects
renderer.effects.apply_preset("prismatic")

# Render 60 frames at 30 fps
print("Rendering animation...")
frames = renderer.render_animation(
    frames=60,
    fps=30,
    time_varying=True,
    callback=lambda i, f: print(f"Frame {i+1}/60", end="\r")
)

print("\nSaving GIF...")

# Save as GIF
renderer.save_animation(frames, "animation.gif", format="gif")
print("Done! animation.gif created")

# Or save as MP4 (requires imageio)
# renderer.save_animation(frames, "animation.mp4", format="mp4")
