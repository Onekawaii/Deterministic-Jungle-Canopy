"""
Sacred Presets 🙏
Pre-configured effect combinations for common visual styles.
"""

PRESETS = {
    "solaris_dream": {
        "effects": ["kaleidoscope", "bloom", "vignette", "color_shift"],
        "params": {
            "kaleidoscope": {"segments": 8},
            "bloom": {"threshold": 0.7, "intensity": 0.4},
            "vignette": {"intensity": 0.6},
            "color_shift": {"hue_shift": 0.1, "sat_mult": 1.3}
        }
    },
    
    "glitch_cathedral": {
        "effects": ["glitch", "scanline", "chromatic_aberration", "noise"],
        "params": {
            "glitch": {"intensity": 0.5, "block_size": 8},
            "scanline": {"frequency": 2, "intensity": 0.4},
            "chromatic_aberration": {"intensity": 0.01},
            "noise": {"amount": 0.08}
        }
    },
    
    "tropical_night": {
        "effects": ["vignette", "duotone", "bloom", "color_shift"],
        "params": {
            "duotone": {
                "dark_color": [0.0, 0.1, 0.3],
                "light_color": [0.9, 0.7, 0.2]
            },
            "bloom": {"threshold": 0.6, "intensity": 0.5},
            "vignette": {"intensity": 0.7, "smoothness": 0.3},
            "color_shift": {"hue_shift": 0.05, "sat_mult": 1.5}
        }
    },
    
    "vhs_prophecy": {
        "effects": ["vhs", "scanline", "noise", "color_shift"],
        "params": {
            "vhs": {"noise_amount": 0.1, "color_bleed": 0.15},
            "scanline": {"frequency": 4, "intensity": 0.3},
            "noise": {"amount": 0.05},
            "color_shift": {"hue_shift": -0.02, "sat_mult": 0.9}
        }
    },
    
    "sacred_geometry": {
        "effects": ["kaleidoscope", "vignette", "posterize", "bloom"],
        "params": {
            "kaleidoscope": {"segments": 6},
            "vignette": {"intensity": 0.4, "smoothness": 0.5},
            "posterize": {"levels": 8},
            "bloom": {"threshold": 0.75, "intensity": 0.35}
        }
    },
    
    "chaos_realm": {
        "effects": ["glitch", "pixelate", "wave", "chromatic_aberration", "film_grain"],
        "params": {
            "glitch": {"intensity": 0.7, "block_size": 12},
            "pixelate": {"block_size": 4},
            "wave": {"amplitude": 15.0, "frequency": 0.03},
            "chromatic_aberration": {"intensity": 0.02},
            "film_grain": {"intensity": 0.15}
        }
    },
    
    "serenity": {
        "effects": ["vignette", "bloom", "color_shift"],
        "params": {
            "vignette": {"intensity": 0.3, "smoothness": 0.6},
            "bloom": {"threshold": 0.8, "intensity": 0.2},
            "color_shift": {"hue_shift": 0.0, "sat_mult": 1.1}
        }
    },
    
    "neon_jungle": {
        "effects": ["bloom", "duotone", "scanline", "color_shift"],
        "params": {
            "bloom": {"threshold": 0.5, "intensity": 0.6},
            "duotone": {
                "dark_color": [0.1, 0.0, 0.2],
                "light_color": [1.0, 0.0, 0.8]
            },
            "scanline": {"frequency": 1, "intensity": 0.15},
            "color_shift": {"hue_shift": 0.15, "sat_mult": 2.0}
        }
    },
    
    "ancient_scroll": {
        "effects": ["vignette", "noise", "color_shift", "posterize"],
        "params": {
            "vignette": {"intensity": 0.8, "smoothness": 0.2},
            "noise": {"amount": 0.12},
            "color_shift": {"hue_shift": -0.1, "sat_mult": 0.7},
            "posterize": {"levels": 6}
        }
    },
    
    "prismatic": {
        "effects": ["chromatic_aberration", "bloom", "color_shift", "glitch"],
        "params": {
            "chromatic_aberration": {"intensity": 0.015, "direction": "radial"},
            "bloom": {"threshold": 0.65, "intensity": 0.5},
            "color_shift": {"hue_shift": 0.2, "sat_mult": 1.4},
            "glitch": {"intensity": 0.2, "block_size": 20}
        }
    }
}


def get_preset(name: str) -> dict:
    """Get a preset by name."""
    if name not in PRESETS:
        raise ValueError(f"Unknown preset: {name}. Available: {list(PRESETS.keys())}")
    return PRESETS[name]


def list_presets() -> list:
    """Get list of all preset names."""
    return list(PRESETS.keys())


def get_preset_description(name: str) -> str:
    """Get a description for a preset."""
    descriptions = {
        "solaris_dream": "Burning sun patterns with kaleidoscopic symmetry",
        "glitch_cathedral": "Digital corruption meets sacred geometry",
        "tropical_night": "Deep blues and warm golds of twilight",
        "vhs_prophecy": "Nostalgic tape artifacts from another dimension",
        "sacred_geometry": "Clean, mathematical beauty with hexagonal symmetry",
        "chaos_realm": "Maximum entropy visual destruction",
        "serenity": "Calm, minimal, meditative",
        "neon_jungle": "Vibrant cyberpunk flora",
        "ancient_scroll": "Weathered parchment of forgotten visions",
        "prismatic": "Light fractured through cosmic crystals"
    }
    return descriptions.get(name, "A visual meditation")
