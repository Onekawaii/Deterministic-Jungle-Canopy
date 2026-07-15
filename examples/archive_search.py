"""
Example: Archive Operations
Saving, searching, and retrieving visual states.
"""
from canopy import CanopyRenderer, Archive
from datetime import datetime, timedelta

# Initialize
archive = Archive("demo_archive.db")
renderer = CanopyRenderer(seed=100)
renderer.bind_archive(archive)

# Generate and save several visions
seeds = [100, 200, 300, 400, 500]
for i, seed in enumerate(seeds):
    renderer.reset(seed=seed)
    renderer.effects.apply_preset(["solaris_dream", "glitch_cathedral", "neon_jungle"][i % 3])
    
    frame = renderer.render_frame()
    renderer.to_image(frame, f"archive_demo_{seed}.png")
    
    entry_id = renderer.save_to_archive(
        name=f"Vision {i+1}",
        tags=["demo", f"seed_{seed}"]
    )
    print(f"Saved vision {i+1} with seed {seed} as entry #{entry_id}")

# Search by tag
print("\n--- Searching for 'demo' tag ---")
results = archive.search(tags=["demo"])
for r in results:
    print(f"  #{r['id']}: {r['name']} (seed: {r['seed']})")

# Search by seed
print("\n--- Searching for seed 300 ---")
results = archive.search(seed=300)
for r in results:
    print(f"  #{r['id']}: {r['name']}")

# Get statistics
print("\n--- Archive Stats ---")
stats = archive.get_stats()
for key, val in stats.items():
    print(f"  {key}: {val}")

# Load a specific entry
print("\n--- Loading entry #2 ---")
renderer.load_from_archive(2)
print(f"Loaded seed: {renderer.rng.seed}")

# Export and import
print("\n--- Export/Import Demo ---")
state = renderer.export_config()
with open("exported_config.json", "w") as f:
    f.write(state)

# Later, import it
renderer.import_config(state)
print(f"Imported seed: {renderer.rng.seed}")
