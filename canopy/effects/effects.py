"""
The Effect Pipeline 🎨
Applies visual transformations to frames in a deterministic manner.
"""
import numpy as np
from typing import Dict, List, Callable, Optional, Any
from ..core.seeded_random import SeededRandom
from .presets import PRESETS


class EffectPipeline:
    """
    Deterministic effect pipeline.
    Each effect uses the shared RNG for reproducible results.
    """
    
    def __init__(self, rng: Optional[SeededRandom] = None):
        """
        Initialize effect pipeline.
        
        Args:
            rng: Seeded RNG for deterministic effect parameters
        """
        self._rng = rng or SeededRandom()
        self._params: Dict[str, Any] = {}
        self._enabled_effects: List[str] = []
        
        # Register built-in effects
        self._effects: Dict[str, Callable] = {
            "chromatic_aberration": self._chromatic_aberration,
            "glitch": self._glitch,
            "scanline": self._scanline,
            "vignette": self._vignette,
            "bloom": self._bloom,
            "noise": self._noise,
            "color_shift": self._color_shift,
            "pixelate": self._pixelate,
            "wave": self._wave,
            "kaleidoscope": self._kaleidoscope,
            "vhs": self._vhs,
            "duotone": self._duotone,
            "negative": self._negative,
            "posterize": self._posterize,
            "film_grain": self._film_grain,
        }
    
    def bind_rng(self, rng: SeededRandom) -> "EffectPipeline":
        """Bind external RNG for deterministic operations."""
        self._rng = rng
        return self
    
    def reset(self) -> "EffectPipeline":
        """Reset all effect parameters."""
        self._params.clear()
        self._enabled_effects.clear()
        return self
    
    def get_config(self) -> dict:
        """Get current effect configuration."""
        return {
            "enabled": self._enabled_effects.copy(),
            "params": self._params.copy()
        }
    
    def set_config(self, config: dict) -> "EffectPipeline":
        """Set effect configuration from dict."""
        self._enabled_effects = config.get("enabled", []).copy()
        self._params = config.get("params", {}).copy()
        return self
    
    def set_param(self, effect: str, param: str, value: Any) -> "EffectPipeline":
        """Set a parameter for a specific effect."""
        if effect not in self._params:
            self._params[effect] = {}
        self._params[effect][param] = value
        if effect not in self._enabled_effects:
            self._enabled_effects.append(effect)
        return self
    
    def get_param(self, effect: str, param: str, default: Any = None) -> Any:
        """Get a parameter value."""
        return self._params.get(effect, {}).get(param, default)
    
    def enable(self, effect: str) -> "EffectPipeline":
        """Enable an effect."""
        if effect not in self._enabled_effects:
            self._enabled_effects.append(effect)
        return self
    
    def disable(self, effect: str) -> "EffectPipeline":
        """Disable an effect."""
        if effect in self._enabled_effects:
            self._enabled_effects.remove(effect)
        return self
    
    def apply(self, effect_name: str, frame: np.ndarray) -> np.ndarray:
        """
        Apply a single effect to a frame.
        
        Args:
            effect_name: Name of the effect
            frame: Input frame (normalized 0-1)
            
        Returns:
            Processed frame
        """
        if effect_name not in self._effects:
            raise ValueError(f"Unknown effect: {effect_name}")
        
        params = self._params.get(effect_name, {})
        return self._effects[effect_name](frame, **params)
    
    def apply_all(self, frame: np.ndarray) -> np.ndarray:
        """
        Apply all enabled effects in order.
        
        Args:
            frame: Input frame
            
        Returns:
            Fully processed frame
        """
        result = frame.copy()
        for effect_name in self._enabled_effects:
            if effect_name in self._effects:
                result = self.apply(effect_name, result)
        return result
    
    def apply_preset(self, preset_name: str) -> "EffectPipeline":
        """Apply a named preset."""
        if preset_name not in PRESETS:
            raise ValueError(f"Unknown preset: {preset_name}")
        
        preset = PRESETS[preset_name]
        self._enabled_effects = preset["effects"].copy()
        self._params = preset.get("params", {}).copy()
        return self
    
    def register_effect(self, name: str, func: Callable) -> "EffectPipeline":
        """Register a custom effect function."""
        self._effects[name] = func
        return self
    
    # ─────────────────────────────────────────────────────────────────
    # Built-in Effects
    # ─────────────────────────────────────────────────────────────────
    
    def _chromatic_aberration(self, frame: np.ndarray, 
                               intensity: float = 0.005,
                               direction: str = "radial") -> np.ndarray:
        """RGB channel separation."""
        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2
        
        yy, xx = np.mgrid[0:h, 0:w]
        
        if direction == "radial":
            dx = (xx - cx) / cx * intensity
            dy = (yy - cy) / cy * intensity
        else:
            dx = intensity * np.sign(xx - cx)
            dy = intensity * np.sign(yy - cy)
        
        def shift(channel, shift_x, shift_y):
            shifted = np.zeros_like(channel)
            src_x = np.clip(xx - shift_x.astype(int), 0, w-1)
            src_y = np.clip(yy - shift_y.astype(int), 0, h-1)
            shifted[yy, xx] = channel[src_y, src_x]
            return shifted
        
        if len(frame.shape) == 3:
            result = np.zeros_like(frame)
            result[:, :, 0] = shift(frame[:, :, 0], dx * w, dy * h)
            result[:, :, 1] = frame[:, :, 1]
            result[:, :, 2] = shift(frame[:, :, 2], -dx * w, -dy * h)
            return result
        return frame
    
    def _glitch(self, frame: np.ndarray, 
                 intensity: float = 0.3,
                 block_size: int = 16) -> np.ndarray:
        """Random block displacement glitch."""
        h, w = frame.shape[:2]
        result = frame.copy()
        
        num_blocks = int(h / block_size * intensity)
        
        for _ in range(num_blocks):
            y_start = int(np.ravel(self._rng.randint(0, h - block_size))[0])
            x_offset = int(np.ravel(self._rng.randint(-20, 20))[0])
            
            block = result[y_start:y_start + block_size, :].copy()
            shifted_block = np.roll(block, x_offset, axis=1)
            result[y_start:y_start + block_size, :] = shifted_block
        
        return result
    
    def _scanline(self, frame: np.ndarray,
                   frequency: int = 2,
                   intensity: float = 0.3) -> np.ndarray:
        """Horizontal scanline effect."""
        h = frame.shape[0]
        scanline = np.ones(h)
        scanline[::frequency] = 1 - intensity
        return frame * scanline[:, np.newaxis]
    
    def _vignette(self, frame: np.ndarray,
                   intensity: float = 0.5,
                   smoothness: float = 0.5) -> np.ndarray:
        """Darken edges."""
        h, w = frame.shape[:2]
        cx, cy = w / 2, h / 2
        
        yy, xx = np.mgrid[0:h, 0:w]
        dist = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
        
        vignette = 1 - intensity * np.clip(dist - smoothness, 0, 1)
        vignette = np.clip(vignette, 0, 1)
        
        if len(frame.shape) == 3:
            return frame * vignette[:, :, np.newaxis]
        return frame * vignette
    
    def _bloom(self, frame: np.ndarray,
                threshold: float = 0.8,
                intensity: float = 0.3) -> np.ndarray:
        """Simple bloom/glow effect."""
        bright_mask = np.max(frame, axis=2) > threshold if len(frame.shape) == 3 else frame > threshold
        bloom = frame.copy()
        bloom[bright_mask] = np.clip(bloom[bright_mask] + intensity, 0, 1)
        return bloom
    
    def _noise(self, frame: np.ndarray,
                amount: float = 0.1) -> np.ndarray:
        """Add random noise."""
        noise = (self._rng.rand(frame.shape) - 0.5) * amount
        return np.clip(frame + noise, 0, 1)
    
    def _color_shift(self, frame: np.ndarray,
                      hue_shift: float = 0.0,
                      sat_mult: float = 1.0) -> np.ndarray:
        """Shift colors in HSV space."""
        from colorsys import rgb_to_hsv, hsv_to_rgb
        
        if len(frame.shape) != 3 or frame.shape[2] != 3:
            return frame
        
        # Convert to HSV per pixel
        hsv = np.zeros_like(frame)
        for i in range(frame.shape[0]):
            for j in range(frame.shape[1]):
                r, g, b = frame[i, j]
                h, s, v = rgb_to_hsv(r, g, b)
                h = (h + hue_shift) % 1.0
                s = np.clip(s * sat_mult, 0, 1)
                hsv[i, j] = hsv_to_rgb(h, s, v)
        
        return hsv
    
    def _pixelate(self, frame: np.ndarray,
                   block_size: int = 8) -> np.ndarray:
        """Reduce resolution in blocks."""
        h, w = frame.shape[:2]
        h_new, w_new = h // block_size, w // block_size
        
        # Reshape and take mean
        small = frame[:h_new * block_size, :w_new * block_size]
        small = small.reshape(h_new, block_size, w_new, block_size, -1)
        small = small.mean(axis=(1, 3))
        
        # Tile back up
        result = np.repeat(np.repeat(small, block_size, axis=0), 
                          block_size, axis=1)
        
        # Handle edge cases
        if result.shape[0] < h or result.shape[1] < w:
            result = np.pad(result, 
                            ((0, h - result.shape[0]), 
                             (0, w - result.shape[1]), 
                             (0, 0)), 
                            mode='edge')
        
        return result[:h, :w]
    
    def _wave(self, frame: np.ndarray,
               amplitude: float = 10.0,
               frequency: float = 0.05) -> np.ndarray:
        """Sine wave distortion."""
        h, w = frame.shape[:2]
        result = np.zeros_like(frame)
        
        for y in range(h):
            offset = int(amplitude * np.sin(y * frequency))
            result[y] = np.roll(frame[y], offset, axis=0)
        
        return result
    
    def _kaleidoscope(self, frame: np.ndarray,
                       segments: int = 6) -> np.ndarray:
        """Mirror folding kaleidoscope."""
        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2
        
        yy, xx = np.mgrid[0:h, 0:w]
        dx, dy = xx - cx, yy - cy
        theta = np.arctan2(dy, dx)
        
        segment_angle = 2 * np.pi / segments
        folded = np.abs(theta % (2 * segment_angle) - segment_angle)
        
        new_x = (cx + np.sqrt(dx**2 + dy**2) * np.cos(folded)).astype(int)
        new_y = (cy + np.sqrt(dx**2 + dy**2) * np.sin(folded)).astype(int)
        
        new_x = np.clip(new_x, 0, w - 1)
        new_y = np.clip(new_y, 0, h - 1)
        
        return frame[new_y, new_x]
    
    def _vhs(self, frame: np.ndarray,
              noise_amount: float = 0.05,
              color_bleed: float = 0.1) -> np.ndarray:
        """VHS/retro tape effect."""
        result = self._noise(frame, noise_amount)
        result = self._scanline(result, frequency=3, intensity=0.2)
        result = self._chromatic_aberration(result, intensity=color_bleed)
        
        # Color shift toward magenta
        if len(result.shape) == 3:
            result[:, :, 0] = np.clip(result[:, :, 0] * 1.1, 0, 1)
            result[:, :, 2] = np.clip(result[:, :, 2] * 1.05, 0, 1)
        
        return result
    
    def _duotone(self, frame: np.ndarray,
                  dark_color: tuple = (0.0, 0.0, 0.5),
                  light_color: tuple = (1.0, 0.8, 0.2)) -> np.ndarray:
        """Two-color gradient mapping."""
        if len(frame.shape) != 3:
            return frame
        
        # Calculate luminance
        lum = 0.299 * frame[:, :, 0] + 0.587 * frame[:, :, 1] + 0.114 * frame[:, :, 2]
        
        dark = np.array(dark_color)
        light = np.array(light_color)
        
        result = dark + lum[:, :, np.newaxis] * (light - dark)
        return np.clip(result, 0, 1)
    
    def _negative(self, frame: np.ndarray) -> np.ndarray:
        """Invert colors."""
        return 1 - frame
    
    def _posterize(self, frame: np.ndarray,
                    levels: int = 4) -> np.ndarray:
        """Reduce color palette."""
        levels_float = float(levels)
        return np.floor(frame * levels_float) / levels_float
    
    def _film_grain(self, frame: np.ndarray,
                     intensity: float = 0.1,
                     size: float = 1.0) -> np.ndarray:
        """Film grain noise."""
        h, w = frame.shape[:2]
        
        # Generate noise at different scales
        for scale in [1.0, 0.5, 0.25]:
            s_h, s_w = max(1, int(h * scale)), max(1, int(w * scale))
            grain = self._rng.rand((s_h, s_w)) * intensity * scale
            grain = np.kron(grain, np.ones((int(1/scale), int(1/scale))))
            grain = grain[:h, :w]
            frame = np.clip(frame + grain[:h, :w, np.newaxis] if len(frame.shape) == 3 
                           else frame + grain[:h, :w], 0, 1)
        
        return frame
