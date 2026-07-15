"""Perception pipeline: uploaded image → normalised SceneGraph."""

from backend.agents.perception import perception
from backend.agents.perception.scene_graph import SceneGraph

__all__ = ["perception", "SceneGraph"]
