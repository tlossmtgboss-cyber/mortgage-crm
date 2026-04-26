"""
DISC + Motivators PDF Report Generator

Generates comprehensive PDF reports mirroring the professional
assessment report format (The Tim Loss Team branded).
"""

import io
import os
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass

# PDF generation - using reportlab
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, Image, ListFlowable, ListItem
    )
    from reportlab.graphics.shapes import Drawing, Rect, Circle, Wedge, String
    from reportlab.graphics.charts.barcharts import VerticalBarChart, HorizontalBarChart
    from reportlab.graphics import renderPDF
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

from .scoring_service import DISCResult
from .wheel_calculator import WheelCalculator, ZONES


@dataclass
class ReportData:
    """Data structure for report generation."""
    candidate_name: str
    assessment_date: datetime
    disc_result: DISCResult
    motivator_scores: Dict[str, int]
    motivator_ranking: Dict[str, int]
    characteristics: Optional[str] = None
    word_sketch: Optional[Dict] = None
    communication_tips: Optional[Dict] = None
    strengths: Optional[list] = None
    stress_behaviors: Optional[list] = None
    improvements: Optional[list] = None


class DISCReportGenerator:
    """Generates PDF reports for DISC + Motivators assessments."""

    # Color scheme
    COLORS = {
        'primary': colors.HexColor('#667eea'),
        'secondary': colors.HexColor('#764ba2'),
        'D': colors.HexColor('#DC2626'),
        'I': colors.HexColor('#F59E0B'),
        'S': colors.HexColor('#10B981'),
        'C': colors.HexColor('#3B82F6'),
        'text': colors.HexColor('#374151'),
        'light_text': colors.HexColor('#6B7280'),
        'background': colors.HexColor('#F9FAFB'),
    }

    MOTIVATOR_COLORS = {
        'aesthetic': colors.HexColor('#8B5CF6'),
        'economic': colors.HexColor('#10B981'),
        'individualistic': colors.HexColor('#F59E0B'),
        'political': colors.HexColor('#EF4444'),
        'altruistic': colors.HexColor('#EC4899'),
        'regulatory': colors.HexColor('#6366F1'),
        'theoretical': colors.HexColor('#3B82F6'),
    }

    def __init__(self):
        if not REPORTLAB_AVAILABLE:
            raise ImportError("reportlab is required for PDF generation. Install with: pip install reportlab")
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Setup custom paragraph styles."""
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading1'],
            fontSize=28,
            textColor=self.COLORS['primary'],
            spaceAfter=20,
            alignment=1,  # Center
        ))
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=18,
            textColor=self.COLORS['primary'],
            spaceBefore=20,
            spaceAfter=12,
        ))
        self.styles.add(ParagraphStyle(
            name='SubHeader',
            parent=self.styles['Heading3'],
            fontSize=14,
            textColor=self.COLORS['text'],
            spaceBefore=12,
            spaceAfter=8,
        ))
        self.styles.add(ParagraphStyle(
            name='BodyText',
            parent=self.styles['Normal'],
            fontSize=11,
            textColor=self.COLORS['text'],
            leading=16,
        ))

    def generate_report(self, data: ReportData) -> bytes:
        """Generate a complete PDF report and return as bytes."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )

        story = []

        # Cover page
        story.extend(self._build_cover_page(data))
        story.append(PageBreak())

        # DISC Overview
        story.extend(self._build_disc_overview(data))
        story.append(PageBreak())

        # DISC Graphs
        story.extend(self._build_disc_graphs(data))
        story.append(PageBreak())

        # Behavioral Pattern View
        story.extend(self._build_wheel_section(data))
        story.append(PageBreak())

        # Characteristics
        if data.characteristics:
            story.extend(self._build_characteristics_section(data))
            story.append(PageBreak())

        # Communication Tips
        if data.communication_tips:
            story.extend(self._build_communication_section(data))
            story.append(PageBreak())

        # Strengths & Stress Behaviors
        story.extend(self._build_strengths_section(data))
        story.append(PageBreak())

        # Motivators Analysis
        story.extend(self._build_motivators_section(data))
        story.append(PageBreak())

        # Summary Page
        story.extend(self._build_summary_section(data))

        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    def _build_cover_page(self, data: ReportData) -> list:
        """Build the cover page."""
        elements = []

        # Logo/Title
        elements.append(Spacer(1, 1*inch))
        elements.append(Paragraph("The Tim Loss Team", self.styles['ReportTitle']))
        elements.append(Spacer(1, 0.25*inch))
        elements.append(Paragraph(
            "DISC + Motivators Assessment Report",
            ParagraphStyle(
                'CoverSubtitle',
                parent=self.styles['Normal'],
                fontSize=20,
                textColor=self.COLORS['secondary'],
                alignment=1,
            )
        ))

        elements.append(Spacer(1, 1*inch))

        # Candidate Info
        elements.append(Paragraph(
            f"<b>{data.candidate_name}</b>",
            ParagraphStyle(
                'CoverName',
                parent=self.styles['Normal'],
                fontSize=24,
                textColor=self.COLORS['text'],
                alignment=1,
            )
        ))

        elements.append(Spacer(1, 0.25*inch))

        elements.append(Paragraph(
            f"Assessment Date: {data.assessment_date.strftime('%B %d, %Y')}",
            ParagraphStyle(
                'CoverDate',
                parent=self.styles['Normal'],
                fontSize=14,
                textColor=self.COLORS['light_text'],
                alignment=1,
            )
        ))

        elements.append(Spacer(1, 1*inch))

        # Quick Summary Box
        disc = data.disc_result
        style_code = f"{disc.adapted_style}/{disc.natural_style}"

        summary_data = [
            ['DISC Style', style_code],
            ['Behavioral Zone', ZONES.get(disc.wheel_zone, {}).get('name', 'Unknown')],
            ['Top Motivator', self._get_top_motivator_name(data.motivator_ranking)],
        ]

        summary_table = Table(summary_data, colWidths=[2*inch, 3*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), self.COLORS['background']),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.COLORS['text']),
            ('FONTSIZE', (0, 0), (-1, -1), 14),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 1, self.COLORS['primary']),
            ('PADDING', (0, 0), (-1, -1), 12),
        ]))

        elements.append(summary_table)

        return elements

    def _build_disc_overview(self, data: ReportData) -> list:
        """Build DISC overview section."""
        elements = []

        elements.append(Paragraph("Understanding Your DISC Profile", self.styles['SectionHeader']))
        elements.append(Paragraph(
            "DISC is a behavioral assessment tool that measures four primary dimensions of behavior: "
            "Dominance (D), Influence (I), Steadiness (S), and Conscientiousness (C). "
            "Understanding your DISC profile helps you communicate more effectively, "
            "work better with others, and leverage your natural strengths.",
            self.styles['BodyText']
        ))

        elements.append(Spacer(1, 0.25*inch))

        # Four dimensions explanation
        dimensions = [
            ('D - Dominance', 'How you handle problems and challenges',
             'Direct, results-oriented, decisive, competitive'),
            ('I - Influence', 'How you handle people and contacts',
             'Enthusiastic, optimistic, collaborative, expressive'),
            ('S - Steadiness', 'How you handle pace and consistency',
             'Patient, reliable, team-oriented, calm'),
            ('C - Conscientiousness', 'How you handle procedures and compliance',
             'Analytical, precise, systematic, quality-focused'),
        ]

        for dim, desc, traits in dimensions:
            elements.append(Paragraph(f"<b>{dim}</b>", self.styles['SubHeader']))
            elements.append(Paragraph(f"{desc}. <i>Traits: {traits}</i>", self.styles['BodyText']))

        return elements

    def _build_disc_graphs(self, data: ReportData) -> list:
        """Build DISC graphs section."""
        elements = []

        elements.append(Paragraph("Your DISC Graphs", self.styles['SectionHeader']))
        elements.append(Paragraph(
            "Your assessment produced two graphs: Adapted Style (how you behave at work) "
            "and Natural Style (your natural tendencies under pressure).",
            self.styles['BodyText']
        ))

        elements.append(Spacer(1, 0.25*inch))

        disc = data.disc_result

        # Graph I - Adapted Style
        elements.append(Paragraph("Graph I: Adapted Style", self.styles['SubHeader']))
        elements.append(self._create_disc_bar_chart({
            'D': disc.adapted_d,
            'I': disc.adapted_i,
            'S': disc.adapted_s,
            'C': disc.adapted_c,
        }, f"Style: {disc.adapted_style}"))

        elements.append(Spacer(1, 0.25*inch))

        # Graph II - Natural Style
        elements.append(Paragraph("Graph II: Natural Style", self.styles['SubHeader']))
        elements.append(self._create_disc_bar_chart({
            'D': disc.natural_d,
            'I': disc.natural_i,
            'S': disc.natural_s,
            'C': disc.natural_c,
        }, f"Style: {disc.natural_style}"))

        return elements

    def _create_disc_bar_chart(self, scores: Dict[str, int], label: str) -> Drawing:
        """Create a DISC bar chart drawing."""
        drawing = Drawing(400, 180)

        # Background
        drawing.add(Rect(0, 0, 400, 180, fillColor=self.COLORS['background'], strokeColor=None))

        # Bars
        bar_width = 60
        bar_spacing = 30
        start_x = 50
        max_height = 120

        for i, (dim, score) in enumerate(scores.items()):
            x = start_x + i * (bar_width + bar_spacing)
            height = (score / 100) * max_height

            # Bar
            drawing.add(Rect(
                x, 30, bar_width, height,
                fillColor=self.COLORS[dim],
                strokeColor=None
            ))

            # Label
            drawing.add(String(
                x + bar_width/2, 10, dim,
                fontSize=14, fontName='Helvetica-Bold',
                fillColor=self.COLORS[dim],
                textAnchor='middle'
            ))

            # Score
            drawing.add(String(
                x + bar_width/2, 35 + height, str(score),
                fontSize=12, fontName='Helvetica-Bold',
                fillColor=self.COLORS['text'],
                textAnchor='middle'
            ))

        # Style label
        drawing.add(String(
            200, 165, label,
            fontSize=14, fontName='Helvetica-Bold',
            fillColor=self.COLORS['primary'],
            textAnchor='middle'
        ))

        return drawing

    def _build_wheel_section(self, data: ReportData) -> list:
        """Build behavioral pattern view wheel section."""
        elements = []

        elements.append(Paragraph("Behavioral Pattern View", self.styles['SectionHeader']))

        disc = data.disc_result
        zone_info = ZONES.get(disc.wheel_zone, {})

        elements.append(Paragraph(
            f"Your behavioral pattern places you in the <b>{zone_info.get('name', 'Unknown')}</b> zone "
            f"(Zone {disc.wheel_zone}, Position {disc.wheel_position}). "
            f"This indicates a primary behavioral tendency of <b>{zone_info.get('primary', 'N/A')}</b>.",
            self.styles['BodyText']
        ))

        elements.append(Spacer(1, 0.25*inch))

        # Zone descriptions
        elements.append(Paragraph("The 8 Behavioral Zones:", self.styles['SubHeader']))

        zone_data = []
        for zone_num, info in ZONES.items():
            is_current = zone_num == disc.wheel_zone
            zone_data.append([
                f"{'>>> ' if is_current else ''}{info['name']}",
                info['primary'],
                'Your Zone' if is_current else ''
            ])

        zone_table = Table(zone_data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch])
        zone_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.COLORS['text']),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['light_text']),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))

        # Highlight current zone
        current_row = disc.wheel_zone - 1
        zone_table.setStyle(TableStyle([
            ('BACKGROUND', (0, current_row), (-1, current_row), self.COLORS['primary']),
            ('TEXTCOLOR', (0, current_row), (-1, current_row), colors.white),
            ('FONTNAME', (0, current_row), (-1, current_row), 'Helvetica-Bold'),
        ]))

        elements.append(zone_table)

        return elements

    def _build_characteristics_section(self, data: ReportData) -> list:
        """Build characteristics section."""
        elements = []

        elements.append(Paragraph("General Characteristics", self.styles['SectionHeader']))

        if data.characteristics:
            # Split into paragraphs
            paragraphs = data.characteristics.split('\n\n')
            for para in paragraphs:
                if para.strip():
                    elements.append(Paragraph(para.strip(), self.styles['BodyText']))
                    elements.append(Spacer(1, 0.1*inch))

        return elements

    def _build_communication_section(self, data: ReportData) -> list:
        """Build communication tips section."""
        elements = []

        elements.append(Paragraph("Communication Tips", self.styles['SectionHeader']))
        elements.append(Paragraph(
            "Use these guidelines when communicating with this person:",
            self.styles['BodyText']
        ))

        elements.append(Spacer(1, 0.25*inch))

        if data.communication_tips:
            dos = data.communication_tips.get('do', [])
            donts = data.communication_tips.get('dont', [])

            # DO section
            if dos:
                elements.append(Paragraph("<b>DO:</b>", self.styles['SubHeader']))
                for item in dos:
                    elements.append(Paragraph(f"✓ {item}", self.styles['BodyText']))

            elements.append(Spacer(1, 0.15*inch))

            # DON'T section
            if donts:
                elements.append(Paragraph("<b>DON'T:</b>", self.styles['SubHeader']))
                for item in donts:
                    elements.append(Paragraph(f"✗ {item}", self.styles['BodyText']))

        return elements

    def _build_strengths_section(self, data: ReportData) -> list:
        """Build strengths and stress behaviors section."""
        elements = []

        elements.append(Paragraph("Strengths & Stress Behaviors", self.styles['SectionHeader']))

        # Strengths
        elements.append(Paragraph("Key Strengths", self.styles['SubHeader']))
        if data.strengths:
            for strength in data.strengths:
                elements.append(Paragraph(f"+ {strength}", self.styles['BodyText']))
        else:
            elements.append(Paragraph("Strengths will be identified through further assessment.", self.styles['BodyText']))

        elements.append(Spacer(1, 0.25*inch))

        # Stress Behaviors
        elements.append(Paragraph("Behaviors Under Stress", self.styles['SubHeader']))
        if data.stress_behaviors:
            for behavior in data.stress_behaviors:
                elements.append(Paragraph(f"- {behavior}", self.styles['BodyText']))
        else:
            elements.append(Paragraph("Stress behaviors will be identified through further assessment.", self.styles['BodyText']))

        elements.append(Spacer(1, 0.25*inch))

        # Areas for Improvement
        elements.append(Paragraph("Areas for Improvement", self.styles['SubHeader']))
        if data.improvements:
            for item in data.improvements:
                elements.append(Paragraph(f"→ {item}", self.styles['BodyText']))
        else:
            elements.append(Paragraph("Growth areas will be identified through further assessment.", self.styles['BodyText']))

        return elements

    def _build_motivators_section(self, data: ReportData) -> list:
        """Build motivators analysis section."""
        elements = []

        elements.append(Paragraph("Motivators Analysis", self.styles['SectionHeader']))
        elements.append(Paragraph(
            "Motivators reveal what drives you - your values, beliefs, and intrinsic motivations. "
            "Understanding your motivators helps explain WHY you do what you do, while DISC explains HOW.",
            self.styles['BodyText']
        ))

        elements.append(Spacer(1, 0.25*inch))

        # Motivators bar chart
        elements.append(self._create_motivators_chart(data.motivator_scores, data.motivator_ranking))

        elements.append(Spacer(1, 0.25*inch))

        # Motivator descriptions
        motivator_descriptions = {
            'aesthetic': ('Aesthetic', 'Driven by beauty, balance, harmony, and creative expression.'),
            'economic': ('Economic', 'Driven by ROI, practicality, and tangible results.'),
            'individualistic': ('Individualistic', 'Driven by independence, uniqueness, and personal significance.'),
            'political': ('Political', 'Driven by control, influence, and power over environment.'),
            'altruistic': ('Altruistic', 'Driven by service to others and eliminating conflict.'),
            'regulatory': ('Regulatory', 'Driven by order, structure, tradition, and established systems.'),
            'theoretical': ('Theoretical', 'Driven by knowledge, learning, understanding, and truth.'),
        }

        # Show ranked motivators
        sorted_motivators = sorted(data.motivator_ranking.items(), key=lambda x: x[1])
        for motivator, rank in sorted_motivators:
            name, desc = motivator_descriptions.get(motivator, (motivator.title(), ''))
            score = data.motivator_scores.get(motivator, 0)
            elements.append(Paragraph(
                f"<b>{rank}. {name}</b> ({score}%): {desc}",
                self.styles['BodyText']
            ))

        return elements

    def _create_motivators_chart(self, scores: Dict[str, int], ranking: Dict[str, int]) -> Drawing:
        """Create motivators horizontal bar chart."""
        drawing = Drawing(500, 200)

        # Background
        drawing.add(Rect(0, 0, 500, 200, fillColor=self.COLORS['background'], strokeColor=None))

        sorted_motivators = sorted(ranking.items(), key=lambda x: x[1])
        bar_height = 20
        bar_spacing = 5
        start_y = 170
        max_width = 280
        label_x = 10

        for i, (motivator, rank) in enumerate(sorted_motivators):
            y = start_y - i * (bar_height + bar_spacing)
            score = scores.get(motivator, 0)
            width = (score / 100) * max_width
            color = self.MOTIVATOR_COLORS.get(motivator, self.COLORS['primary'])

            # Label
            drawing.add(String(
                label_x, y + bar_height/2 - 4, f"{rank}. {motivator.title()}",
                fontSize=10, fontName='Helvetica',
                fillColor=self.COLORS['text'],
            ))

            # Bar
            drawing.add(Rect(
                120, y, width, bar_height,
                fillColor=color,
                strokeColor=None
            ))

            # Score
            drawing.add(String(
                125 + width, y + bar_height/2 - 4, f"{score}%",
                fontSize=10, fontName='Helvetica-Bold',
                fillColor=self.COLORS['text'],
            ))

        return drawing

    def _build_summary_section(self, data: ReportData) -> list:
        """Build summary section."""
        elements = []

        elements.append(Paragraph("Summary", self.styles['SectionHeader']))

        disc = data.disc_result
        zone_info = ZONES.get(disc.wheel_zone, {})
        top_motivator = self._get_top_motivator_name(data.motivator_ranking)

        summary_text = f"""
        <b>{data.candidate_name}</b> demonstrates a <b>{disc.adapted_style}/{disc.natural_style}</b>
        DISC style pattern, placing them in the <b>{zone_info.get('name', 'Unknown')}</b> behavioral zone.

        Their primary behavioral tendency is <b>{zone_info.get('primary', 'N/A')}</b>, indicating they
        naturally approach situations with a focus on {self._get_zone_focus(disc.wheel_zone)}.

        Their top motivator is <b>{top_motivator}</b>, which drives their decisions and behaviors.

        This unique combination of behavioral style and motivators provides insight into how
        {data.candidate_name} will perform, communicate, and be motivated in a professional setting.
        """

        elements.append(Paragraph(summary_text, self.styles['BodyText']))

        elements.append(Spacer(1, 0.5*inch))

        # Report footer
        elements.append(Paragraph(
            f"Report generated by The Tim Loss Team on {datetime.now().strftime('%B %d, %Y')}",
            ParagraphStyle(
                'Footer',
                parent=self.styles['Normal'],
                fontSize=10,
                textColor=self.COLORS['light_text'],
                alignment=1,
            )
        ))

        return elements

    def _get_top_motivator_name(self, ranking: Dict[str, int]) -> str:
        """Get the name of the top ranked motivator."""
        for motivator, rank in ranking.items():
            if rank == 1:
                return motivator.title()
        return 'Unknown'

    def _get_zone_focus(self, zone: int) -> str:
        """Get focus description for a zone."""
        focuses = {
            1: 'achieving results and overcoming challenges',
            2: 'directing others and driving action',
            3: 'persuading and inspiring people',
            4: 'promoting ideas and building enthusiasm',
            5: 'building relationships and supporting others',
            6: 'maintaining stability and providing support',
            7: 'coordinating details and ensuring accuracy',
            8: 'analyzing data and ensuring quality',
        }
        return focuses.get(zone, 'balanced approach to tasks and people')


async def generate_disc_report(
    candidate_name: str,
    disc_result: DISCResult,
    motivator_scores: Dict[str, int],
    motivator_ranking: Dict[str, int],
    generated_content: Optional[Dict] = None
) -> bytes:
    """
    Generate a DISC + Motivators PDF report.

    Args:
        candidate_name: Name of the candidate
        disc_result: DISCResult object with scores
        motivator_scores: Dict of motivator dimension scores
        motivator_ranking: Dict of motivator rankings (1-7)
        generated_content: Optional AI-generated content

    Returns:
        PDF bytes
    """
    generator = DISCReportGenerator()

    data = ReportData(
        candidate_name=candidate_name,
        assessment_date=datetime.now(),
        disc_result=disc_result,
        motivator_scores=motivator_scores,
        motivator_ranking=motivator_ranking,
        characteristics=generated_content.get('characteristics') if generated_content else None,
        word_sketch=generated_content.get('word_sketch') if generated_content else None,
        communication_tips=generated_content.get('communication_tips') if generated_content else None,
        strengths=generated_content.get('strengths') if generated_content else None,
        stress_behaviors=generated_content.get('stress_behaviors') if generated_content else None,
        improvements=generated_content.get('improvements') if generated_content else None,
    )

    return generator.generate_report(data)
