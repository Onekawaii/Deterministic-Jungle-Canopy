"""
The Shader Bridge 🌉
Connects the sacred GLSL shaders from GlitchCam to the Python Canopy.
"""
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Callable
import re


class ShaderBridge:
    """
    Translates GLSL shaders into Python-native operations.
    The ancient runes become Pythonic incantations.
    """
    
    def __init__(self, shaders_dir: Optional[str] = None):
        """
        Initialize the shader bridge.
        
        Args:
            shaders_dir: Path to directory containing .frag shader files
        """
        self.shaders_dir = shaders_dir
        self._loaded_shaders: Dict[str, str] = {}
        self._compiled_effects: Dict[str, Callable] = {}
    
    def load_shader(self, name: str) -> str:
        """Load a GLSL shader from file."""
        if name in self._loaded_shaders:
            return self._loaded_shaders[name]
        
        if not self.shaders_dir:
            raise ValueError("No shaders_dir configured")
        
        shader_path = Path(self.shaders_dir) / f"{name}.frag"
        if not shader_path.exists():
            raise FileNotFoundError(f"Shader not found: {shader_path}")
        
        with open(shader_path) as f:
            content = f.read()
        
        self._loaded_shaders[name] = content
        return content
    
    def parse_uniforms(self, shader_code: str) -> Dict[str, str]:
        """Extract uniform declarations from shader code."""
        uniforms = {}
        for match in re.finditer(r'uniform\s+(\w+)\s+(\w+)\s*;', shader_code):
            uniforms[match.group(2)] = match.group(1)
        return uniforms
    
    def parse_hash_functions(self, shader_code: str) -> List[str]:
        """Extract hash function implementations."""
        functions = []
        # Match function definitions like float hash(vec2 p) {...}
        pattern = r'(float|vec2|vec3|vec4)\s+hash[^\{]*\{[^}]*\}'
        for match in re.finditer(pattern, shader_code, re.MULTILINE | re.DOTALL):
            functions.append(match.group(0))
        return functions
    
    def glsl_to_python_noise(self, shader_code: str) -> Callable:
        """
        Convert GLSL noise functions to Python.
        
        This is a simplified translator that handles the common patterns
        found in the GlitchCam shaders.
        """
        # Extract hash function if present
        hash_funcs = self.parse_hash_functions(shader_code)
        
        # Create Python equivalents
        def hash1(p: np.ndarray) -> np.ndarray:
            """Python version of GLSL hash(vec2 p) -> float"""
            if len(p.shape) == 1:
                p = p.reshape(-1, 2)
            result = np.zeros(p.shape[0])
            for i, (px, py) in enumerate(p):
                result[i] = np.sin(px * 127.1 + py * 311.7) * 43758.5453
            return np.mod(result, 1.0)
        
        def hash2(p: np.ndarray) -> np.ndarray:
            """Python version of GLSL hash2(vec2 p) -> vec2"""
            if len(p.shape) == 1:
                p = p.reshape(-1, 2)
            result = np.zeros((p.shape[0], 2))
            for i, (px, py) in enumerate(p):
                val1 = np.sin(px * 127.1 + py * 311.7) * 43758.5453
                val2 = np.sin(px * 269.5 + py * 183.3) * 43758.5453
                result[i] = [np.mod(val1, 1.0), np.mod(val2, 1.0)]
            return result
        
        return hash1, hash2
    
    def compile_voronoi(self, shader_name: str = "voronoi") -> Callable:
        """
        Compile a Voronoi shader into a Python function.
        
        Returns a function that takes an image and intensity parameter.
        """
        shader = self.load_shader(shader_name)
        uniforms = self.parse_uniforms(shader)
        
        # Parse scale and intensity defaults
        scale_default = 5.0
        intensity_default = 0.5
        
        def voronoi_effect(image: np.ndarray, 
                           intensity: float = intensity_default,
                           scale: float = 1.0,
                           rng: Optional[np.random.Generator] = None) -> np.ndarray:
            """
            Apply Voronoi cellular distortion.
            
            Args:
                image: Input image array
                intensity: Effect strength (0-1)
                scale: Number of cells
                rng: Optional seeded RNG for determinism
            """
            h, w = image.shape[:2]
            
            # Generate random cell centers
            if rng:
                centers = rng.random((int(scale ** 2), 2)) * np.array([w, h])
            else:
                centers = np.random.random((int(scale ** 2), 2)) * np.array([w, h])
            
            # Calculate nearest center for each pixel
            yy, xx = np.mgrid[0:h, 0:w]
            pixels = np.column_stack([xx.ravel(), yy.ravel()])
            dists = np.linalg.norm(
                pixels[:, np.newaxis] - centers, 
                axis=2
            )
            min_dists = np.min(dists, axis=1).reshape(h, w)
            
            # Normalize distances
            max_dist = np.max(min_dists) + 1e-6
            voronoi_map = min_dists / max_dist
            
            # Apply as color modulation
            if len(image.shape) == 3:
                # Apply per channel with slight variation
                for c in range(min(image.shape[2], 3)):
                    offset = c * 0.1 * intensity
                    image[:, :, c] = image[:, :, c] * (1 + (voronoi_map - 0.5) * intensity * 0.6 + offset)
            else:
                image = image * (1 + (voronoi_map - 0.5) * intensity * 0.6)
            
            return np.clip(image, 0, 1)
        
        return voronoi_effect
    
    def compile_kaleidoscope(self, shader_name: str = "kaleidoscope_6") -> Callable:
        """
        Compile a kaleidoscope shader into a Python function.
        """
        def kaleidoscope_effect(image: np.ndarray,
                                 intensity: float = 1.0,
                                 segments: int = 6) -> np.ndarray:
            """
            Apply kaleidoscope folding effect.
            
            Args:
                image: Input image array
                intensity: Effect strength (0-1)
                segments: Number of mirror segments
            """
            h, w = image.shape[:2]
            cx, cy = w // 2, h // 2
            
            yy, xx = np.mgrid[0:h, 0:w]
            dx = xx - cx
            dy = yy - cy
            
            # Convert to polar
            r = np.sqrt(dx**2 + dy**2)
            theta = np.arctan2(dy, dx)
            
            # Fold angle
            segment_angle = 2 * np.pi / segments
            folded_theta = np.abs(theta % (2 * segment_angle) - segment_angle)
            
            # Calculate folded coordinates
            new_x = (cx + r * np.cos(folded_theta)).astype(int)
            new_y = (cy + r * np.sin(folded_theta)).astype(int)
            
            # Clip to bounds
            new_x = np.clip(new_x, 0, w - 1)
            new_y = np.clip(new_y, 0, h - 1)
            
            # Sample from folded coordinates
            folded = image[new_y, new_x]
            
            # Blend with original
            result = image * (1 - intensity) + folded * intensity
            return np.clip(result, 0, 1)
        
        return kaleidoscope_effect
    
    def compile_glitch_hold(self, shader_name: str = "glitch_hold") -> Callable:
        """
        Compile a glitch-hold shader into a Python function.
        """
        def glitch_effect(image: np.ndarray,
                          intensity: float = 0.3,
                          time: float = 0.0,
                          rng: Optional[np.random.Generator] = None) -> np.ndarray:
            """
            Apply horizontal glitch displacement.
            
            Args:
                image: Input image array
                intensity: Effect strength (0-1)
                time: Time value for animation
                rng: Optional seeded RNG for determinism
            """
            h, w = image.shape[:2]
            result = image.copy()
            
            # Number of glitch lines based on intensity
            num_lines = int(h * intensity * 0.3)
            
            if rng:
                line_indices = rng.integers(0, h, num_lines)
                shifts = (rng.random(num_lines) - 0.5) * w * intensity * 0.2
            else:
                line_indices = np.random.randint(0, h, num_lines)
                shifts = (np.random.random(num_lines) - 0.5) * w * intensity * 0.2
            
            # Apply horizontal shifts
            for i, (line_idx, shift) in enumerate(zip(line_indices, shifts)):
                shift_pixels = int(shift)
                result[line_idx, :] = np.roll(result[line_idx, :], shift_pixels, axis=0)
            
            return result
        
        return glitch_effect
    
    def compile_all(self) -> Dict[str, Callable]:
        """
        Compile all available shaders into Python functions.
        
        Returns:
            Dictionary mapping shader names to compiled functions
        """
        self._compiled_effects = {
            "voronoi": self.compile_voronoi(),
            "kaleidoscope": self.compile_kaleidoscope(),
            "glitch_hold": self.compile_glitch_hold(),
        }
        return self._compiled_effects
    
    def get_effect(self, name: str) -> Optional[Callable]:
        """Get a compiled effect function by name."""
        if not self._compiled_effects:
            self.compile_all()
        return self._compiled_effects.get(name)


# Quick shader translation rules for common GLSL patterns
GLSL_TO_NUMPY = {
    # Math operations
    r'fract\(': 'np.mod(',
    r'sin\(': 'np.sin(',
    r'cos\(': 'np.cos(',
    r'tan\(': 'np.tan(',
    r'abs\(': 'np.abs(',
    r'sqrt\(': 'np.sqrt(',
    r'pow\(': 'np.power(',
    r'min\(': 'np.minimum(',
    r'max\(': 'np.maximum(',
    r'clamp\(': 'np.clip(',
    r'mix\(': 'np.where(',  # Linear interpolate
    r'length\(': 'np.linalg.norm(',
    r'dot\(([^,]+),\s*([^)]+)\s*\)': r'np.dot(\1, \2)',
    r'normalize\(': 'lambda v: v / np.linalg.norm(v)',
    r'mod\(([^,]+),\s*([^)]+)\)': r'np.mod(\1, \2)',
    
    # Vector construction
    r'vec2\(([^)]+)\)': r'np.array([\1])',
    r'vec3\(([^)]+)\)': r'np.array([\1])',
    r'vec4\(([^)]+)\)': r'np.array([\1])',
}


def translate_glsl_expression(expr: str) -> str:
    """
    Translate a GLSL expression to NumPy/Python.
    
    Args:
        expr: GLSL expression string
        
    Returns:
        Python/NumPy equivalent
    """
    result = expr
    
    # Apply translation rules
    for glsl_pattern, numpy_replacement in GLSL_TO_NUMPY.items():
        result = re.sub(glsl_pattern, numpy_replacement, result)
    
    return result


def extract_main_function(shader_code: str) -> str:
    """Extract the main() function body from GLSL shader."""
    match = re.search(r'void\s+main\s*\(\s*\)\s*\{([^}]+)\}', 
                      shader_code, re.DOTALL)
    if match:
        return match.group(1)
    return ""


def shader_to_numpy(shader_code: str) -> Callable:
    """
    Attempt to convert a simple GLSL shader to a NumPy function.
    
    This is a best-effort translation for simple shaders.
    Complex shaders may require manual implementation.
    """
    main_body = extract_main_function(shader_code)
    
    # This is a simplified implementation
    # Full GLSL to Python translation would require a proper parser
    
    def generated_effect(image: np.ndarray, **uniforms) -> np.ndarray:
        # Placeholder - in practice, this would use the translated code
        return image
    
    return generated_effect
