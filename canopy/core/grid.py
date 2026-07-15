"""
Grid Manipulation System 🌐
The flexible mesh that bends, stretches, and folds the visual plane.
"""
import numpy as np
from typing import Tuple, Callable, Optional
from .seeded_random import SeededRandom


class GridManipulator:
    """
    Real-time grid manipulation for visual warping.
    Treats the visual space as a flexible mesh that can be deformed.
    """
    
    def __init__(self, width: int, height: int, rng: Optional[SeededRandom] = None):
        """
        Initialize grid manipulator.
        
        Args:
            width: Grid width
            height: Grid height
            rng: Seeded random number generator for deterministic operations
        """
        self.width = width
        self.height = height
        
        # Create coordinate grids
        self._x = np.linspace(0, 1, width)
        self._y = np.linspace(0, 1, height)
        self._xx, self._yy = np.meshgrid(self._x, self._y)
        
        # Current displacement field
        self._dx = np.zeros_like(self._xx)
        self._dy = np.zeros_like(self._yy)
        
        # Reference to RNG (can be shared with renderer)
        self._rng = rng or SeededRandom()
    
    def bind_rng(self, rng: SeededRandom) -> None:
        """Bind an external RNG for deterministic operations."""
        self._rng = rng
    
    def reset(self) -> None:
        """Reset grid to identity transformation."""
        self._dx = np.zeros_like(self._xx)
        self._dy = np.zeros_like(self._yy)
    
    def apply_displacement(self, image: np.ndarray) -> np.ndarray:
        """
        Apply current displacement field to an image.
        
        Args:
            image: Input image array
            
        Returns:
            Warped image
        """
        # Calculate new coordinates
        new_x = self._xx + self._dx
        new_y = self._yy + self._dy
        
        # Clamp to valid range
        new_x = np.clip(new_x, 0, 1)
        new_y = np.clip(new_y, 0, 1)
        
        # Map to pixel coordinates
        px = (new_x * (self.width - 1)).astype(np.float32)
        py = (new_y * (self.height - 1)).astype(np.float32)
        
        # Bilinear interpolation
        from scipy.ndimage import map_coordinates
        coords = np.array([py, px])
        
        if len(image.shape) == 3:
            # Multi-channel image
            warped = np.zeros_like(image)
            for c in range(image.shape[2]):
                warped[:, :, c] = map_coordinates(
                    image[:, :, c], coords, order=1, mode='reflect'
                )
            return warped
        else:
            return map_coordinates(image, coords, order=1, mode='reflect')
    
    def add_wave(self, amplitude: float, frequency: float, phase: float = 0.0,
                  direction: str = "x", damping: Optional[Callable] = None) -> "GridManipulator":
        """
        Add a sinusoidal wave distortion.
        
        Args:
            amplitude: Wave amplitude
            frequency: Wave frequency
            phase: Phase offset
            direction: 'x', 'y', or 'both'
            damping: Optional function(fraction) for edge damping
        """
        t = self._x if direction in ("x", "both") else self._y
        wave = amplitude * np.sin(2 * np.pi * frequency * t + phase)
        
        if direction in ("x", "both"):
            self._dx += wave
        if direction in ("y", "both"):
            self._dy += wave
        
        return self
    
    def add_radial_wave(self, amplitude: float, frequency: float, 
                         center: Optional[Tuple[float, float]] = None) -> "GridManipulator":
        """Add radial wave distortion from a center point."""
        cx, cy = center or (0.5, 0.5)
        cx_arr = self._xx - cx
        cy_arr = self._yy - cy
        r = np.sqrt(cx_arr**2 + cy_arr**2)
        
        wave = amplitude * np.sin(2 * np.pi * frequency * r)
        self._dx += wave * (cx_arr / (r + 1e-6))
        self._dy += wave * (cy_arr / (r + 1e-6))
        
        return self
    
    def add_voronoi_deformation(self, scale: float = 5.0, 
                                 intensity: float = 0.1) -> "GridManipulator":
        """
        Add Voronoi-based cellular deformation.
        
        Args:
            scale: Number of cells
            intensity: Deformation strength
        """
        # Generate random cell centers using seeded RNG
        n_cells = int(scale ** 2)
        centers = self._rng.rand((n_cells, 2))
        centers = np.round(centers * scale).astype(int)
        
        # Find closest center for each grid point
        scaled_x = self._xx * scale
        scaled_y = self._yy * scale
        
        # Displacement based on nearest center offset
        self._dx += self._rng.rand() * intensity * (self._rng.rand() - 0.5)
        self._dy += self._rng.rand() * intensity * (self._rng.rand() - 0.5)
        
        return self
    
    def add_turbulence(self, octaves: int = 4, persistence: float = 0.5,
                        scale: float = 1.0, intensity: float = 0.1) -> "GridManipulator":
        """
        Add organic turbulence using fractal noise.
        
        Args:
            octaves: Number of noise layers
            persistence: Amplitude decay per octave
            scale: Noise frequency
            intensity: Distortion strength
        """
        noise_x = self._rng.fbm((self.height, self.width), octaves, persistence)
        noise_y = self._rng.fbm((self.height, self.width), octaves, persistence)
        
        self._dx += (noise_x - 0.5) * intensity * scale
        self._dy += (noise_y - 0.5) * intensity * scale
        
        return self
    
    def add_kaleidoscope(self, segments: int = 6, 
                          center: Optional[Tuple[float, float]] = None) -> "GridManipulator":
        """
        Add kaleidoscope folding effect.
        
        Args:
            segments: Number of mirror segments
            center: Center point (x, y) in [0, 1] range
        """
        cx, cy = center or (0.5, 0.5)
        
        # Convert to polar from center
        dx = self._xx - cx
        dy = self._yy - cy
        r = np.sqrt(dx**2 + dy**2)
        theta = np.arctan2(dy, dx)
        
        # Fold angle
        segment_angle = 2 * np.pi / segments
        folded_theta = np.abs(theta % (2 * segment_angle) - segment_angle)
        
        # Reconstruct coordinates
        new_x = cx + r * np.cos(folded_theta)
        new_y = cy + r * np.sin(folded_theta)
        
        self._dx = new_x - self._xx
        self._dy = new_y - self._yy
        
        return self
    
    def add_glitch_lines(self, density: float = 0.1, 
                          max_shift: float = 0.05) -> "GridManipulator":
        """
        Add horizontal glitch line displacements.
        
        Args:
            density: Fraction of lines that glitch (0-1)
            max_shift: Maximum horizontal shift
        """
        num_lines = int(self.height * density)
        line_indices = self._rng.choice(self.height, num_lines, replace=False)
        
        shifts = (self._rng.rand(num_lines) - 0.5) * max_shift
        
        for i, line_idx in enumerate(line_indices):
            self._dx[line_idx, :] = shifts[i]
        
        return self
    
    def add_pixel_sort(self, threshold: float = 0.5, direction: str = "horizontal",
                        sort_by: str = "brightness") -> "GridManipulator":
        """
        Add pixel sorting displacement (records parameters for later application).
        
        Note: This is a marker for effect application, not a direct displacement.
        """
        # This would be applied during render pass
        return self
    
    def add_shear(self, x_factor: float = 0.0, 
                   y_factor: float = 0.0) -> "GridManipulator":
        """Add affine shear transformation."""
        self._dx += self._xx * x_factor
        self._dy += self._yy * y_factor
        return self
    
    def add_rotation(self, angle: float, 
                      center: Optional[Tuple[float, float]] = None) -> "GridManipulator":
        """Add rotation around center point."""
        cx, cy = center or (0.5, 0.5)
        
        dx = self._xx - cx
        dy = self._yy - cy
        
        cos_a = np.cos(angle)
        sin_a = np.sin(angle)
        
        new_dx = dx * cos_a - dy * sin_a - dx
        new_dy = dx * sin_a + dy * cos_a - dy
        
        self._dx += new_dx
        self._dy += new_dy
        
        return self
    
    def add_zoom(self, factor: float, 
                  center: Optional[Tuple[float, float]] = None) -> "GridManipulator":
        """Add zoom/pinch distortion."""
        cx, cy = center or (0.5, 0.5)
        
        dx = self._xx - cx
        dy = self._yy - cy
        r = np.sqrt(dx**2 + dy**2)
        
        # Smooth zoom falloff
        zoom_map = factor * np.exp(-r * 3)
        
        self._dx -= dx * zoom_map
        self._dy -= dy * zoom_map
        
        return self
    
    def add_ripple(self, amplitude: float, frequency: float,
                    center: Optional[Tuple[float, float]] = None,
                    decay: float = 0.5) -> "GridManipulator":
        """
        Add concentric ripple distortion.
        
        Args:
            amplitude: Wave amplitude
            frequency: Wave frequency
            center: Center point
            decay: Distance-based amplitude decay
        """
        cx, cy = center or (0.5, 0.5)
        
        dx = self._xx - cx
        dy = self._yy - cy
        r = np.sqrt(dx**2 + dy**2)
        
        wave = amplitude * np.sin(2 * np.pi * frequency * r)
        decay_map = np.exp(-r * decay)
        
        self._dx += wave * decay_map * (dx / (r + 1e-6))
        self._dy += wave * decay_map * (dy / (r + 1e-6))
        
        return self
    
    def add_bulge(self, amplitude: float, radius: float = 0.3,
                  center: Optional[Tuple[float, float]] = None) -> "GridManipulator":
        """Add bulge/pinch distortion."""
        cx, cy = center or (0.5, 0.5)
        
        dx = self._xx - cx
        dy = self._yy - cy
        r = np.sqrt(dx**2 + dy**2)
        
        # Smooth bulge falloff
        bulge = amplitude * np.exp(-((r - radius) ** 2) / (2 * (radius / 3) ** 2))
        
        self._dx += dx * bulge
        self._dy += dy * bulge
        
        return self
    
    def compose(self, other: "GridManipulator") -> "GridManipulator":
        """
        Compose this grid with another (apply other's displacement on top).
        """
        if self.width != other.width or self.height != other.height:
            raise ValueError("Grid dimensions must match for composition")
        
        combined = GridManipulator(self.width, self.height, self._rng)
        combined._dx = self._dx + other._dx
        combined._dy = self._dy + other._dy
        return combined
    
    def get_displacement(self) -> Tuple[np.ndarray, np.ndarray]:
        """Get current displacement field."""
        return self._dx.copy(), self._dy.copy()
    
    def set_displacement(self, dx: np.ndarray, dy: np.ndarray) -> None:
        """Set displacement field directly."""
        self._dx = dx.copy()
        self._dy = dy.copy()
    
    def to_dict(self) -> dict:
        """Serialize grid state."""
        return {
            "width": self.width,
            "height": self.height,
            "dx": self._dx.tolist(),
            "dy": self._dy.tolist()
        }
    
    @classmethod
    def from_dict(cls, data: dict, rng: Optional[SeededRandom] = None) -> "GridManipulator":
        """Deserialize grid state."""
        gm = cls(data["width"], data["height"], rng)
        gm._dx = np.array(data["dx"])
        gm._dy = np.array(data["dy"])
        return gm
