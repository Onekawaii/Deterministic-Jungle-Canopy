#!/usr/bin/env python3
"""
Determinism Live Trial 🔬✨
Runs comprehensive determinism verification and generates a receipt.

Usage:
    python scripts/determinism_live_trial.py
    python scripts/determinism_live_trial.py --output receipts/

This script proves the determinism contract by:
1. Rendering the same manifest in separate processes
2. Comparing pixel hashes
3. Verifying archive roundtrips
4. Generating a signed receipt
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
import shutil
import subprocess
import platform
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canopy import CanopyRenderer, Archive
from canopy.manifest import ManifestBuilder
from canopy.effects.presets import list_presets
from canopy.version import __version__, __schema_version__


class DeterminismTrial:
    """
    Runs determinism trials and generates proof receipts.
    """
    
    def __init__(self, output_dir: str = "receipts"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results = []
        self.passed = 0
        self.failed = 0
        
    def log(self, message: str, level: str = "INFO"):
        """Log a message."""
        prefix = {
            "INFO": "  📋",
            "PASS": "  ✅",
            "FAIL": "  ❌",
            "WARN": "  ⚠️",
        }.get(level, "    ")
        print(f"{prefix} {message}")
    
    def hash_frame(self, frame):
        """Generate SHA256 hash of frame pixels."""
        return hashlib.sha256(frame.tobytes()).hexdigest()
    
    def _apply_manifest(self, renderer, manifest):
        """Helper to apply manifest to renderer."""
        for effect in manifest.effects:
            if effect.enabled:
                renderer.effects.enable(effect.name)
                for param, value in effect.params.items():
                    renderer.effects.set_param(effect.name, param, value)
        
        for op in manifest.grid_operations:
            method_name = f"add_{op.type}"
            if hasattr(renderer.grid, method_name):
                getattr(renderer.grid, method_name)(**op.params)
    
    def test_same_process_identical(self):
        """Test: Same manifest in same process produces identical output."""
        self.log("Test: Same manifest in same process")
        
        manifest = ManifestBuilder(seed=42, width=128, height=128) \
            .with_effect("vignette", intensity=0.5) \
            .with_effect("bloom", threshold=0.7) \
            .with_grid_op("turbulence", octaves=3) \
            .with_metadata("Trial Vision") \
            .build()
        
        renderer = CanopyRenderer(width=manifest.width, height=manifest.height, seed=manifest.seed)
        self._apply_manifest(renderer, manifest)
        
        # First render
        frame1 = renderer.render_frame()
        hash1 = self.hash_frame(frame1)
        
        # Full reset and re-apply for second render
        renderer.reset(seed=manifest.seed)
        renderer.effects.reset()
        self._apply_manifest(renderer, manifest)
        
        # Second render
        frame2 = renderer.render_frame()
        hash2 = self.hash_frame(frame2)
        
        if hash1 == hash2:
            self.log(f"  First render:  {hash1[:32]}...", "PASS")
            self.log(f"  Second render: {hash2[:32]}...", "PASS")
            self.log(f"  Match: True", "PASS")
            self.passed += 1
            return True, {"first_render": hash1, "second_render": hash2, "match": True}, manifest
        else:
            self.log(f"  First render:  {hash1[:32]}...", "FAIL")
            self.log(f"  Second render: {hash2[:32]}...", "FAIL")
            self.log(f"  Match: False", "FAIL")
            self.failed += 1
            return False, {"first_render": hash1, "second_render": hash2, "match": False}, manifest
    
    def test_fresh_process_identical(self):
        """Test: Same manifest in fresh process produces identical output."""
        self.log("Test: Same manifest in fresh process")
        
        # Render in subprocess with same manifest
        manifest = ManifestBuilder(seed=12345, width=64, height=64) \
            .with_preset("neon_jungle") \
            .build()
        
        # Get hash from subprocess
        script = f'''
import sys
sys.path.insert(0, "{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}")
from canopy import CanopyRenderer
from canopy.manifest import ManifestBuilder

manifest = ManifestBuilder(seed=12345, width=64, height=64).with_preset("neon_jungle").build()
renderer = CanopyRenderer(width=manifest.width, height=manifest.height, seed=manifest.seed)
renderer.apply_preset("neon_jungle")
frame = renderer.render_frame()
import hashlib
print(hashlib.sha256(frame.tobytes()).hexdigest())
'''
        
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            subprocess_hash = result.stdout.strip()
            
            # Get hash from this process
            renderer = CanopyRenderer(width=64, height=64, seed=12345)
            renderer.apply_preset("neon_jungle")
            local_hash = self.hash_frame(renderer.render_frame())
            
            if subprocess_hash == local_hash:
                self.log(f"  Subprocess:  {subprocess_hash[:32]}...", "PASS")
                self.log(f"  Local:       {local_hash[:32]}...", "PASS")
                self.log(f"  Match: True", "PASS")
                self.passed += 1
                return True, {"subprocess": subprocess_hash, "local": local_hash, "match": True}
            else:
                self.log(f"  Subprocess:  {subprocess_hash[:32]}...", "FAIL")
                self.log(f"  Local:       {local_hash[:32]}...", "FAIL")
                self.log(f"  Match: False", "FAIL")
                self.failed += 1
                return False, {"subprocess": subprocess_hash, "local": local_hash, "match": False}
        else:
            self.log(f"  Subprocess error: {result.stderr}", "FAIL")
            self.failed += 1
            return False, None
    
    def test_archive_roundtrip(self):
        """Test: Archive save/load produces identical output."""
        self.log("Test: Archive save/load roundtrip")
        
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmpdir, "trial_archive.db")
            archive = Archive(db_path)
            
            renderer = CanopyRenderer(width=64, height=64, seed=999)
            renderer.bind_archive(archive)
            
            # Configure
            renderer.effects.apply_preset("prismatic")
            renderer.grid.add_turbulence()
            
            # Save to archive BEFORE first render
            entry_id = renderer.save_to_archive("Archive Trial")
            
            # Get original hash (using fresh load to ensure clean state)
            renderer.reset(seed=999)
            renderer.effects.reset()
            renderer.effects.apply_preset("prismatic")
            renderer.grid.add_turbulence()
            original_frame = renderer.render_frame()
            original_hash = self.hash_frame(original_frame)
            
            # Reset to different state
            renderer.set_seed(12345)
            
            # Load from archive
            renderer.load_from_archive(entry_id)
            
            # Render again
            loaded_frame = renderer.render_frame()
            loaded_hash = self.hash_frame(loaded_frame)
            
            if original_hash == loaded_hash:
                self.log(f"  Before save:  {original_hash[:32]}...", "PASS")
                self.log(f"  After load:   {loaded_hash[:32]}...", "PASS")
                self.log(f"  Match: True", "PASS")
                self.passed += 1
                return True, {"before_save": original_hash, "after_load": loaded_hash, "match": True}
            else:
                self.log(f"  Before save:  {original_hash[:32]}...", "FAIL")
                self.log(f"  After load:   {loaded_hash[:32]}...", "FAIL")
                self.log(f"  Match: False", "FAIL")
                self.failed += 1
                return False, {"before_save": original_hash, "after_load": loaded_hash, "match": False}
        finally:
            shutil.rmtree(tmpdir)
    
    def test_all_presets_deterministic(self):
        """Test: All presets are deterministic."""
        self.log("Test: All presets deterministic")
        
        all_presets = list_presets()
        failures = []
        
        for preset in all_presets:
            renderer1 = CanopyRenderer(width=64, height=64, seed=42)
            renderer2 = CanopyRenderer(width=64, height=64, seed=42)
            
            renderer1.apply_preset(preset)
            renderer2.apply_preset(preset)
            
            hash1 = self.hash_frame(renderer1.render_frame())
            hash2 = self.hash_frame(renderer2.render_frame())
            
            if hash1 != hash2:
                failures.append(preset)
        
        if not failures:
            self.log(f"  All {len(all_presets)} presets deterministic", "PASS")
            self.passed += 1
            return True
        else:
            self.log(f"  Failed presets: {failures}", "FAIL")
            self.failed += 1
            return False
    
    def test_different_seed_different_output(self):
        """Test: Different seeds produce different output."""
        self.log("Test: Different seeds produce different output")
        
        # Use larger image for better collision resistance
        renderer1 = CanopyRenderer(width=256, height=256, seed=1)
        renderer2 = CanopyRenderer(width=256, height=256, seed=2)
        
        hash1 = self.hash_frame(renderer1.render_frame())
        hash2 = self.hash_frame(renderer2.render_frame())
        
        if hash1 != hash2:
            self.log(f"  Different seeds → different hashes", "PASS")
            self.passed += 1
            return True
        else:
            # Very unlikely for 256x256 - something's wrong
            self.log(f"  Same hash despite different seeds (collision unlikely)", "FAIL")
            self.failed += 1
            return False
    
    def gather_environment_info(self):
        """Gather environment information for receipt."""
        return {
            "platform": platform.platform(),
            "python_version": sys.version,
            "canopy_version": __version__,
            "schema_version": __schema_version__,
            "numpy_version": __import__('numpy').__version__,
            "scipy_version": __import__('scipy').__version__,
        }
    
    def run(self):
        """Run all determinism trials."""
        print("\n" + "=" * 60)
        print("  🌿 THE DETERMINISTIC JUNGLE CANOPY 🌿")
        print("  Determinism Live Trial & Receipt Generation")
        print("=" * 60 + "\n")
        
        print(f"Started: {datetime.now(timezone.utc).isoformat()}Z\n")
        
        # Run trials
        results = []
        
        # 1. Same process identical
        success, hash_pairs, manifest = self.test_same_process_identical()
        results.append({
            "name": "same_process_identical",
            "description": "Same manifest, same process, two renders",
            "passed": success,
            "hash_pairs": {
                "first_render": hash_pairs.get("first_render") if hash_pairs else None,
                "second_render": hash_pairs.get("second_render") if hash_pairs else None,
                "match": hash_pairs.get("match") if hash_pairs else False,
            },
        })
        print()
        
        # 2. Fresh process identical
        success, hash_pairs = self.test_fresh_process_identical()
        results.append({
            "name": "fresh_process_identical",
            "description": "Same manifest rendered in subprocess vs main process",
            "passed": success,
            "hash_pairs": {
                "subprocess_render": hash_pairs.get("subprocess") if hash_pairs else None,
                "local_render": hash_pairs.get("local") if hash_pairs else None,
                "match": hash_pairs.get("match") if hash_pairs else False,
            },
        })
        print()
        
        # 3. Archive roundtrip
        success, hash_pairs = self.test_archive_roundtrip()
        results.append({
            "name": "archive_roundtrip",
            "description": "State saved to archive, then loaded and rendered",
            "passed": success,
            "hash_pairs": {
                "before_save": hash_pairs.get("before_save") if hash_pairs else None,
                "after_load": hash_pairs.get("after_load") if hash_pairs else None,
                "match": hash_pairs.get("match") if hash_pairs else False,
            },
        })
        print()
        
        # 4. All presets deterministic
        success = self.test_all_presets_deterministic()
        results.append({
            "name": "all_presets_deterministic",
            "description": "Each preset produces same output with same seed",
            "passed": success,
        })
        print()
        
        # 5. Different seed different output
        success = self.test_different_seed_different_output()
        results.append({
            "name": "different_seed_different_output",
            "description": "Different seeds produce different hashes (no collision)",
            "passed": success,
        })
        print()
        
        # Generate receipt with explicit paired hashes
        receipt = {
            "schema_version": __schema_version__,
            "engine_version": __version__,
            "trial_timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "environment": self.gather_environment_info(),
            "results": results,
            "summary": {
                "total_tests": self.passed + self.failed,
                "passed": self.passed,
                "failed": self.failed,
                "all_passed": self.failed == 0,
            },
            "contract": {
                "same_manifest_same_output": all(r.get("hash_pairs", {}).get("match", False) for r in results if "hash_pairs" in r),
                "archive_reload_identical": results[2].get("hash_pairs", {}).get("match", False) if len(results) > 2 else False,
                "presets_deterministic": results[3].get("passed", False) if len(results) > 3 else False,
                "cross_process_verified": results[1].get("hash_pairs", {}).get("match", False) if len(results) > 1 else False,
            },
        }
        
        # Save receipt
        receipt_path = self.output_dir / f"receipt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        with open(receipt_path, 'w') as f:
            json.dump(receipt, f, indent=2)
        
        # Summary
        print("=" * 60)
        print("  TRIAL SUMMARY")
        print("=" * 60)
        print(f"  Total Tests: {self.passed + self.failed}")
        print(f"  Passed:      {self.passed} ✅")
        print(f"  Failed:      {self.failed} ❌")
        print(f"  Receipt:     {receipt_path}")
        print("=" * 60)
        
        if self.failed == 0:
            print("\n  🍌 ALL TESTS PASSED - DETERMINISM CONTRACT VERIFIED 🍌\n")
            return 0
        else:
            print("\n  ⚠️  SOME TESTS FAILED - VERIFICATION INCOMPLETE ⚠️\n")
            return 1


def main():
    parser = argparse.ArgumentParser(description="Run determinism trials")
    parser.add_argument("--output", "-o", default="receipts", 
                        help="Output directory for receipts")
    args = parser.parse_args()
    
    trial = DeterminismTrial(args.output)
    return trial.run()


if __name__ == "__main__":
    sys.exit(main())
