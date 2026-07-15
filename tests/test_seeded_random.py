"""
Test: Seeded Random Number Generator
Verifies that the deterministic RNG produces identical output for the same seed.
"""
import pytest
import numpy as np
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canopy.core.seeded_random import SeededRandom


class TestSeededRandomDeterminism:
    """Tests for deterministic RNG behavior."""
    
    def test_same_seed_produces_same_sequence(self):
        """Identical seeds must produce identical random sequences."""
        rng1 = SeededRandom(seed=42)
        rng2 = SeededRandom(seed=42)
        
        # Generate the same sequence
        seq1 = rng1.rand(100)
        seq2 = rng2.rand(100)
        
        np.testing.assert_array_equal(seq1, seq2, 
            err_msg="Same seed must produce identical sequence")
    
    def test_reset_restores_state(self):
        """Reset must restore the RNG to its initial state."""
        rng = SeededRandom(seed=42)
        
        # Generate some values
        original = rng.rand(50)
        
        # Generate more values (different)
        after = rng.rand(50)
        
        # Reset
        rng.reset()
        
        # Generate same values as original
        reset = rng.rand(50)
        
        np.testing.assert_array_equal(original, reset,
            err_msg="Reset must restore exact initial state")
    
    def test_save_and_restore_state(self):
        """State save/restore must be exact."""
        rng = SeededRandom(seed=42)
        
        # Generate initial sequence
        initial = rng.rand(30)
        
        # Save state
        rng.save_state()
        
        # Generate more
        intermediate = rng.rand(20)
        
        # Restore and generate again
        rng.restore_state()
        restored = rng.rand(20)
        
        np.testing.assert_array_equal(intermediate, restored,
            err_msg="Restore must produce same sequence as before save")
    
    def test_different_seeds_produce_different_sequences(self):
        """Different seeds must produce different sequences."""
        rng1 = SeededRandom(seed=1)
        rng2 = SeededRandom(seed=2)
        
        seq1 = rng1.rand(100)
        seq2 = rng2.rand(100)
        
        # They should not be identical (extremely unlikely to happen by chance)
        assert not np.array_equal(seq1, seq2), \
            "Different seeds must produce different sequences"
    
    def test_all_random_functions_are_deterministic(self):
        """All RNG functions must be deterministic."""
        seed = 12345
        
        rng1 = SeededRandom(seed=seed)
        rng2 = SeededRandom(seed=seed)
        
        # Test all major functions
        funcs = [
            ("rand", lambda r: r.rand(50)),
            ("randn", lambda r: r.randn(50)),
            ("randint", lambda r: r.randint(0, 100, 50)),
            ("permutation", lambda r: r.permutation(100)[:50]),
        ]
        
        for name, func in funcs:
            result1 = func(rng1)
            result2 = func(rng2)
            np.testing.assert_array_equal(result1, result2,
                err_msg=f"{name} must be deterministic")
    
    def test_fbm_noise_is_deterministic(self):
        """FBM (Fractal Brownian Motion) noise must be deterministic."""
        rng1 = SeededRandom(seed=42)
        rng2 = SeededRandom(seed=42)
        
        shape = (100, 100)
        
        noise1 = rng1.fbm(shape, octaves=4)
        noise2 = rng2.fbm(shape, octaves=4)
        
        np.testing.assert_array_almost_equal(noise1, noise2, decimal=10,
            err_msg="FBM noise must be deterministic")
    
    def test_perlin_noise_is_deterministic(self):
        """Perlin noise must be deterministic."""
        rng1 = SeededRandom(seed=42)
        rng2 = SeededRandom(seed=42)
        
        shape = (64, 64)
        
        noise1 = rng1.perlin_noise(shape)
        noise2 = rng2.perlin_noise(shape)
        
        np.testing.assert_array_almost_equal(noise1, noise2, decimal=10,
            err_msg="Perlin noise must be deterministic")
    
    def test_state_dict_serialization(self):
        """State dict must allow exact reconstruction."""
        rng1 = SeededRandom(seed=42)
        
        # Generate some values
        rng1.rand(100)
        rng1.randn(50)
        
        # Get state
        state = rng1.get_state_dict()
        
        # Create new RNG from state
        rng2 = SeededRandom.from_state_dict(state)
        
        # Both should produce identical next values
        next1 = rng1.rand(50)
        next2 = rng2.rand(50)
        
        np.testing.assert_array_equal(next1, next2,
            err_msg="State dict must allow exact reconstruction")
    
    def test_seed_property_returns_correct_value(self):
        """Seed property must return the configured seed."""
        rng = SeededRandom(seed=12345)
        assert rng.seed == 12345, "Seed property must return configured seed"


class TestSeededRandomEdgeCases:
    """Edge case tests for the RNG."""
    
    def test_zero_seed(self):
        """Zero seed must be valid and deterministic."""
        rng1 = SeededRandom(seed=0)
        rng2 = SeededRandom(seed=0)
        
        seq1 = rng1.rand(100)
        seq2 = rng2.rand(100)
        
        np.testing.assert_array_equal(seq1, seq2)
    
    def test_large_seed(self):
        """Large seed values must work."""
        large_seed = 2**31 - 1
        rng1 = SeededRandom(seed=large_seed)
        rng2 = SeededRandom(seed=large_seed)
        
        seq1 = rng1.rand(100)
        seq2 = rng2.rand(100)
        
        np.testing.assert_array_equal(seq1, seq2)
    
    def test_empty_shape(self):
        """Empty shape must not cause errors."""
        rng = SeededRandom(seed=42)
        result = rng.rand(())
        assert result.shape == (), "Empty shape should produce scalar"
    
    def test_state_stack_isolation(self):
        """Multiple save/restore must work correctly."""
        rng = SeededRandom(seed=42)
        
        # Save multiple states
        rng.rand(10)
        rng.save_state()
        
        state1 = rng.rand(20)
        
        rng.save_state()
        state2 = rng.rand(30)
        
        rng.save_state()
        state3 = rng.rand(40)
        
        # Restore in reverse order
        rng.restore_state()
        restored3 = rng.rand(40)
        
        rng.restore_state()
        restored2 = rng.rand(30)
        
        rng.restore_state()
        restored1 = rng.rand(20)
        
        np.testing.assert_array_equal(state3, restored3)
        np.testing.assert_array_equal(state2, restored2)
        np.testing.assert_array_equal(state1, restored1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
