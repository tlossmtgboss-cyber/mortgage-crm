"""
Behavioral Pattern View Wheel Calculator

Maps DISC scores to the 8-zone, 81-position wheel visualization.

Zones:
1. Implementor (High D, Low I)
2. Conductor (High D, High I)
3. Persuader (High I, High D)
4. Promoter (High I, Low D)
5. Relater (High S, High I)
6. Supporter (High S, Low I)
7. Coordinator (High C, High S)
8. Analyzer (High C, Low S)
"""

from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import math


class WheelZone(Enum):
    """The 8 behavioral zones on the DISC wheel."""
    IMPLEMENTOR = 1
    CONDUCTOR = 2
    PERSUADER = 3
    PROMOTER = 4
    RELATER = 5
    SUPPORTER = 6
    COORDINATOR = 7
    ANALYZER = 8


@dataclass
class WheelPosition:
    """Position on the behavioral pattern wheel."""
    zone: int
    zone_name: str
    position: int  # 1-81 for granular positioning
    angle: float  # Degrees from top (0-360)
    radius: float  # Distance from center (0-1)
    description: str


class WheelCalculator:
    """
    Calculator for Behavioral Pattern View wheel position.

    The wheel divides behavior into 8 zones based on DISC dimensions,
    with 81 possible positions for granular placement.
    """

    ZONE_INFO = {
        1: {
            "name": "Implementor",
            "primary": "D",
            "secondary": None,
            "angle_start": 315,
            "angle_end": 360,
            "description": "Takes decisive action to achieve results. Efficient, practical, and focused on outcomes.",
            "strengths": ["Gets things done", "Efficient", "Practical", "Independent"],
            "challenges": ["May overlook people", "Can be blunt", "Impatient with process"],
        },
        2: {
            "name": "Conductor",
            "primary": "D",
            "secondary": "I",
            "angle_start": 0,
            "angle_end": 45,
            "description": "Leads with both drive and charisma. Inspires action while maintaining focus on goals.",
            "strengths": ["Natural leader", "Motivating", "Goal-oriented", "Confident"],
            "challenges": ["May dominate", "Competitive", "Fast-paced for some"],
        },
        3: {
            "name": "Persuader",
            "primary": "I",
            "secondary": "D",
            "angle_start": 45,
            "angle_end": 90,
            "description": "Influences through enthusiasm and relationships. Combines people skills with drive.",
            "strengths": ["Persuasive", "Enthusiastic", "Networker", "Optimistic"],
            "challenges": ["May oversell", "Scattered focus", "Overlooks details"],
        },
        4: {
            "name": "Promoter",
            "primary": "I",
            "secondary": None,
            "angle_start": 90,
            "angle_end": 135,
            "description": "Creates excitement and builds relationships. Naturally engaging and positive.",
            "strengths": ["Engaging", "Creative", "Team builder", "Positive energy"],
            "challenges": ["May lack follow-through", "Dislikes routine", "Emotional"],
        },
        5: {
            "name": "Relater",
            "primary": "S",
            "secondary": "I",
            "angle_start": 135,
            "angle_end": 180,
            "description": "Builds warm relationships and supports others. Patient, caring, and collaborative.",
            "strengths": ["Supportive", "Good listener", "Team player", "Patient"],
            "challenges": ["May avoid conflict", "Slow to decide", "Too accommodating"],
        },
        6: {
            "name": "Supporter",
            "primary": "S",
            "secondary": None,
            "angle_start": 180,
            "angle_end": 225,
            "description": "Provides steady, reliable support. Consistent, loyal, and dependable.",
            "strengths": ["Reliable", "Loyal", "Consistent", "Calming presence"],
            "challenges": ["Resists change", "May suppress opinions", "Needs security"],
        },
        7: {
            "name": "Coordinator",
            "primary": "C",
            "secondary": "S",
            "angle_start": 225,
            "angle_end": 270,
            "description": "Organizes with precision and patience. Methodical, thorough, and quality-focused.",
            "strengths": ["Organized", "Thorough", "Quality-focused", "Systematic"],
            "challenges": ["May be inflexible", "Slow to start", "Perfectionistic"],
        },
        8: {
            "name": "Analyzer",
            "primary": "C",
            "secondary": None,
            "angle_start": 270,
            "angle_end": 315,
            "description": "Analyzes thoroughly before acting. Precise, accurate, and detail-oriented.",
            "strengths": ["Accurate", "Analytical", "Objective", "Precise"],
            "challenges": ["Analysis paralysis", "Critical", "May seem distant"],
        },
    }

    def __init__(self):
        pass

    def calculate_position(
        self,
        d: int,
        i: int,
        s: int,
        c: int
    ) -> WheelPosition:
        """
        Calculate wheel position from DISC scores.

        Args:
            d, i, s, c: DISC dimension scores (0-100)

        Returns:
            WheelPosition with zone and position details
        """
        # Calculate angle based on DISC quadrant
        angle = self._calculate_angle(d, i, s, c)

        # Determine zone from angle
        zone = self._angle_to_zone(angle)

        # Calculate radius (distance from center = intensity)
        radius = self._calculate_radius(d, i, s, c)

        # Calculate position number (1-81)
        position = self._calculate_position_number(angle, radius)

        zone_info = self.ZONE_INFO.get(zone, {})

        return WheelPosition(
            zone=zone,
            zone_name=zone_info.get("name", "Unknown"),
            position=position,
            angle=angle,
            radius=radius,
            description=zone_info.get("description", ""),
        )

    def _calculate_angle(self, d: int, i: int, s: int, c: int) -> float:
        """
        Calculate angle on wheel from DISC scores.

        The wheel is organized:
        - Top (0°): D-I quadrant
        - Right (90°): I-S quadrant
        - Bottom (180°): S-C quadrant
        - Left (270°): C-D quadrant
        """
        # Normalize scores
        total = d + i + s + c
        if total == 0:
            return 0.0

        d_norm = d / 100
        i_norm = i / 100
        s_norm = s / 100
        c_norm = c / 100

        # Calculate x and y coordinates
        # D pulls toward top-left, I toward top-right
        # S pulls toward bottom-right, C toward bottom-left
        x = (i_norm - s_norm + d_norm - c_norm) / 2
        y = (d_norm - s_norm + i_norm - c_norm) / 2

        # Convert to angle (0 = top, clockwise)
        angle = math.degrees(math.atan2(x, y))
        if angle < 0:
            angle += 360

        return round(angle, 1)

    def _angle_to_zone(self, angle: float) -> int:
        """Convert angle to zone number (1-8)."""
        # Zones are 45° each, starting at 315° (Implementor)
        normalized_angle = (angle + 45) % 360
        zone = int(normalized_angle / 45) + 1
        return max(1, min(8, zone))

    def _calculate_radius(self, d: int, i: int, s: int, c: int) -> float:
        """
        Calculate radius (intensity) from DISC scores.

        Higher differentiation between scores = larger radius.
        """
        scores = [d, i, s, c]
        max_score = max(scores)
        min_score = min(scores)

        # Radius based on differentiation
        differentiation = (max_score - min_score) / 100

        # Also consider overall intensity
        avg = sum(scores) / 4
        intensity = abs(max_score - avg) / 50

        radius = (differentiation + intensity) / 2
        return min(1.0, max(0.2, radius))

    def _calculate_position_number(self, angle: float, radius: float) -> int:
        """
        Calculate position number 1-81 based on angle and radius.

        The 81 positions create a 9x9 grid on the wheel:
        - 9 angular segments (40° each)
        - 9 radial segments
        """
        # Angular segment (1-9)
        angular_segment = int((angle / 360) * 9) + 1
        angular_segment = max(1, min(9, angular_segment))

        # Radial segment (1-9)
        radial_segment = int(radius * 9) + 1
        radial_segment = max(1, min(9, radial_segment))

        # Combine into position number
        position = (angular_segment - 1) * 9 + radial_segment
        return max(1, min(81, position))

    def get_zone_info(self, zone: int) -> Dict:
        """Get detailed information about a zone."""
        return self.ZONE_INFO.get(zone, {})

    def get_zone_compatibility(self, zone1: int, zone2: int) -> Dict:
        """
        Get compatibility information between two zones.

        Returns:
            Dict with compatibility score and tips
        """
        # Adjacent zones have higher natural compatibility
        diff = abs(zone1 - zone2)
        if diff > 4:
            diff = 8 - diff  # Wrap around

        if diff == 0:
            compatibility = "High"
            score = 0.9
            tips = ["Similar styles - understand each other well", "May need someone different for balance"]
        elif diff == 1:
            compatibility = "Good"
            score = 0.8
            tips = ["Complementary styles", "Build on shared strengths"]
        elif diff == 2:
            compatibility = "Moderate"
            score = 0.6
            tips = ["Some adjustment needed", "Focus on common goals"]
        elif diff == 3:
            compatibility = "Challenging"
            score = 0.4
            tips = ["Different approaches", "Requires intentional adaptation"]
        else:
            compatibility = "Opposite"
            score = 0.3
            tips = ["Very different styles", "Can complement if both adapt", "Potential for friction"]

        return {
            "compatibility": compatibility,
            "score": score,
            "tips": tips,
            "zone1_info": self.ZONE_INFO.get(zone1, {}),
            "zone2_info": self.ZONE_INFO.get(zone2, {}),
        }

    def get_wheel_svg_data(self, position: WheelPosition) -> Dict:
        """
        Get data for rendering the wheel SVG.

        Returns coordinates and styling for the wheel visualization.
        """
        # Convert angle to radians (adjusting for SVG coordinate system)
        angle_rad = math.radians(position.angle - 90)

        # Calculate x, y on unit circle
        x = math.cos(angle_rad) * position.radius
        y = math.sin(angle_rad) * position.radius

        # Scale to SVG coordinates (assuming 200x200 viewbox, center at 100,100)
        svg_x = 100 + x * 80
        svg_y = 100 + y * 80

        return {
            "center_x": 100,
            "center_y": 100,
            "marker_x": svg_x,
            "marker_y": svg_y,
            "angle": position.angle,
            "radius": position.radius,
            "zone": position.zone,
            "zone_name": position.zone_name,
            "zone_color": self._get_zone_color(position.zone),
        }

    def _get_zone_color(self, zone: int) -> str:
        """Get color for zone (for visualization)."""
        colors = {
            1: "#DC2626",  # Red - Implementor
            2: "#EA580C",  # Orange - Conductor
            3: "#F59E0B",  # Amber - Persuader
            4: "#FBBF24",  # Yellow - Promoter
            5: "#84CC16",  # Lime - Relater
            6: "#22C55E",  # Green - Supporter
            7: "#14B8A6",  # Teal - Coordinator
            8: "#3B82F6",  # Blue - Analyzer
        }
        return colors.get(zone, "#6B7280")


# Module-level alias used by report_generator.py
ZONES = WheelCalculator.ZONE_INFO
