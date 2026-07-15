"""
Seeded Random Number Generator 🌱
The root of the great tree. The same seed always yields the same branch.
"""
import numpy as np
from typing import Optional, Tuple, Any


class SeededRandom:
    """
    Deterministic random number generator.
    Given the same seed, it will always produce the same sequence.
    """
    
    def __init__(self, seed: Optional[int] = None):
        """
        Initialize with a seed.
        
        Args:
            seed: Integer seed. If None, uses system entropy.
        """
        self._seed = seed if seed is not None else np.random.randint(0, 2**31)
        self._rng = np.random.Generator(np.random.PCG64(self._seed))
        self._state_stack = []
    
    @property
    def seed(self) -> int:
        """Return the current seed."""
        return self._seed
    
    def reset(self) -> None:
        """Reset to the initial seed state."""
        self._rng = np.random.Generator(np.random.PCG64(self._seed))
    
    def save_state(self) -> Any:
        """Save current RNG state to a stack."""
        self._state_stack.append(self._rng.bit_generator.state)
    
    def restore_state(self) -> None:
        """Restore the most recently saved state."""
        if self._state_stack:
            self._rng.bit_generator.state = self._state_stack.pop()
    
    def discard_state(self) -> None:
        """Discard the most recently saved state without restoring."""
        if self._state_stack:
            self._state_stack.pop()
    
    def rand(self, shape: Tuple[int, ...] = (1,)) -> np.ndarray:
        """Generate uniform random values in [0, 1)."""
        return self._rng.random(shape)
    
    def randint(self, low: int, high: int, shape: Tuple[int, ...] = (1,)) -> np.ndarray:
        """Generate random integers in [low, high)."""
        return self._rng.integers(low, high, shape)
    
    def randn(self, shape: Tuple[int, ...] = (1,)) -> np.ndarray:
        """Generate standard normal distribution values."""
        return self._rng.standard_normal(shape)
    
    def choice(self, a: int or list, size: Tuple[int, ...] = (1,)) -> np.ndarray:
        """Randomly choose from array."""
        return self._rng.choice(a, size)
    
    def permutation(self, n: int) -> np.ndarray:
        """Return a random permutation of [0, n)."""
        return self._rng.permutation(n)
    
    def shuffle(self, array: np.ndarray) -> None:
        """Shuffle array in-place."""
        self._rng.shuffle(array)
    
    def point_in_circle(self, num_points: int) -> np.ndarray:
        """Generate random points inside a unit circle."""
        r = np.sqrt(self.rand(num_points))
        theta = 2 * np.pi * self.rand(num_points)
        return np.column_stack((
            r * np.cos(theta),
            r * np.sin(theta)
        ))
    
    def point_on_sphere(self, num_points: int, dim: int = 2) -> np.ndarray:
        """Generate uniformly distributed points on a unit hypersphere."""
        points = self.randn((num_points, dim))
        norms = np.linalg.norm(points, axis=1, keepdims=True)
        return points / norms
    
    def perlin_noise(self, shape: Tuple[int, int], scale: float = 1.0) -> np.ndarray:
        """
        Generate Perlin-like noise using seeded randomness.
        
        Args:
            shape: Output shape (height, width)
            scale: Frequency scale (cells per output unit)
            
        Returns:
            Noise array with values in [-1, 1]
        """
        height, width = shape
        
        # Number of cells in each dimension (based on scale)
        n_cells_y = max(1, int(scale))
        n_cells_x = max(1, int(scale))
        
        # Grid has one more point than cells
        grid_h = n_cells_y + 1
        grid_w = n_cells_x + 1
        
        # Generate random gradient vectors
        raw_gradients = self.randn((grid_h, grid_w, 2))
        norms = np.linalg.norm(raw_gradients, axis=2, keepdims=True)
        gradients = raw_gradients / (norms + 1e-8)
        
        # Fade function (6t^5 - 15t^4 + 10t^3)
        def fade(t):
            return 6*t**5 - 15*t**4 + 10*t**3
        
        # Linear interpolation
        def lerp(a, b, t):
            return a + t * (b - a)
        
        noise = np.zeros(shape)
        
        for i in range(height):
            for j in range(width):
                # Position in continuous grid coordinates
                # Add 0.5 to sample at cell centers, not corners
                x = (j / width) * n_cells_x + 0.5
                y = (i / height) * n_cells_y + 0.5
                
                # Cell indices
                xi = int(np.floor(x)) % n_cells_x
                yi = int(np.floor(y)) % n_cells_y
                
                # Fractional position within cell [0, 1)
                xf = x - np.floor(x)
                yf = y - np.floor(y)
                
                # Fade curves
                u = fade(xf)
                v = fade(yf)
                
                # Gradient indices (clamp to grid bounds)
                g00_y = min(yi, grid_h - 1)
                g00_x = min(xi, grid_w - 1)
                g10_y = min(yi, grid_h - 1)
                g10_x = min(xi + 1, grid_w - 1)
                g01_y = min(yi + 1, grid_h - 1)
                g01_x = min(xi, grid_w - 1)
                g11_y = min(yi + 1, grid_h - 1)
                g11_x = min(xi + 1, grid_w - 1)
                
                # Gradient dot products
                g00 = gradients[g00_y, g00_x, 0] * xf + gradients[g00_y, g00_x, 1] * yf
                g10 = gradients[g10_y, g10_x, 0] * (xf - 1) + gradients[g10_y, g10_x, 1] * yf
                g01 = gradients[g01_y, g01_x, 0] * xf + gradients[g01_y, g01_x, 1] * (yf - 1)
                g11 = gradients[g11_y, g11_x, 0] * (xf - 1) + gradients[g11_y, g11_x, 1] * (yf - 1)
                
                # Interpolate
                x1 = lerp(g00, g10, u)
                x2 = lerp(g01, g11, u)
                noise[i, j] = lerp(x1, x2, v)
        
        return noise
    
    def fbm(self, shape: Tuple[int, int], octaves: int = 4, persistence: float = 0.5) -> np.ndarray:
        """
        Fractal Brownian Motion - layered noise for organic textures.
        
        Args:
            shape: Output shape
            octaves: Number of noise layers
            persistence: Amplitude reduction per octave
            
        Returns:
            FBM noise array normalized to [0, 1]
        """
        noise = np.zeros(shape)
        amplitude = 1.0
        frequency = 1.0
        max_value = 0.0
        
        for _ in range(octaves):
            layer = self.perlin_noise(
                shape, 
                scale=1.0 / frequency
            )
            noise += amplitude * layer
            max_value += amplitude
            amplitude *= persistence
            frequency *= 2
        
        # Normalize to [0, 1]
        noise = (noise / max_value + 1) / 2
        return np.clip(noise, 0, 1)
    
    def get_state_dict(self) -> dict:
        """Get full state for serialization."""
        return {
            "seed": self._seed,
            "rng_state": self._rng.bit_generator.state,
            "state_stack": self._state_stack.copy()
        }
    
    @classmethod
    def from_state_dict(cls, state: dict) -> "SeededRandom":
        """Reconstruct from serialized state."""
        rng = cls(state["seed"])
        rng._rng.bit_generator.state = state["rng_state"]
        rng._state_stack = state["state_stack"].copy()
        return rng
