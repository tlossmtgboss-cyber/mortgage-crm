"""
Video Project Service
Handles video project creation, script generation, and content management.
"""

import os
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class VideoProjectService:
    """Service for managing video projects and content generation."""

    def __init__(self):
        self.llm_provider = os.getenv("LLM_PROVIDER", "anthropic")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

    # =========================================================================
    # PROJECT CRUD
    # =========================================================================

    def create_project(
        self,
        db: Session,
        user_id: int,
        title: str,
        source_type: str,
        source_text: str,
        organization_id: Optional[int] = None,
        brand_template_id: Optional[int] = None,
        voice_profile_id: Optional[int] = None,
        target_duration_seconds: int = 60,
        target_formats: List[str] = None,
        tags: List[str] = None,
        category: Optional[str] = None,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        campaign_id: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a new video project."""
        try:
            if target_formats is None:
                target_formats = ["portrait_9x16"]
            if tags is None:
                tags = []

            # Get default template/voice if not specified
            if not brand_template_id:
                default_template = db.execute(text("""
                    SELECT id FROM video_brand_templates
                    WHERE is_default = true AND is_active = true
                    LIMIT 1
                """)).fetchone()
                if default_template:
                    brand_template_id = default_template[0]

            if not voice_profile_id:
                default_voice = db.execute(text("""
                    SELECT id FROM video_voice_profiles
                    WHERE is_default = true AND is_active = true
                    LIMIT 1
                """)).fetchone()
                if default_voice:
                    voice_profile_id = default_voice[0]

            result = db.execute(text("""
                INSERT INTO video_projects (
                    organization_id, created_by, title, source_type, source_text,
                    brand_template_id, voice_profile_id, target_duration_seconds,
                    target_formats, tags, category, lead_id, loan_id, campaign_id,
                    status, created_at, updated_at
                ) VALUES (
                    :org_id, :user_id, :title, :source_type, :source_text,
                    :template_id, :voice_id, :duration,
                    :formats, :tags, :category, :lead_id, :loan_id, :campaign_id,
                    'draft', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                RETURNING id
            """), {
                "org_id": organization_id,
                "user_id": user_id,
                "title": title,
                "source_type": source_type,
                "source_text": source_text,
                "template_id": brand_template_id,
                "voice_id": voice_profile_id,
                "duration": target_duration_seconds,
                "formats": json.dumps(target_formats),
                "tags": json.dumps(tags),
                "category": category,
                "lead_id": lead_id,
                "loan_id": loan_id,
                "campaign_id": campaign_id
            })

            project_id = result.fetchone()[0]
            db.commit()

            return self.get_project(db, project_id)

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error creating video project: {e}")
            raise

    def get_project(self, db: Session, project_id: int) -> Optional[Dict[str, Any]]:
        """Get a video project by ID."""
        result = db.execute(text("""
            SELECT
                p.*,
                bt.name as template_name,
                vp.name as voice_name
            FROM video_projects p
            LEFT JOIN video_brand_templates bt ON bt.id = p.brand_template_id
            LEFT JOIN video_voice_profiles vp ON vp.id = p.voice_profile_id
            WHERE p.id = :id
        """), {"id": project_id}).fetchone()

        if not result:
            return None

        return self._row_to_dict(result)

    def list_projects(
        self,
        db: Session,
        organization_id: Optional[int] = None,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List video projects with filters. Returns (projects, total_count)."""
        params = {"limit": limit, "offset": offset}
        filters = []

        if organization_id:
            filters.append("p.organization_id = :org_id")
            params["org_id"] = organization_id
        if user_id:
            filters.append("p.created_by = :user_id")
            params["user_id"] = user_id
        if status:
            filters.append("p.status = :status")
            params["status"] = status
        if category:
            filters.append("p.category = :category")
            params["category"] = category
        if search:
            filters.append("(p.title ILIKE :search OR p.source_text ILIKE :search)")
            params["search"] = f"%{search}%"

        where_clause = " AND ".join(filters) if filters else "1=1"

        # Get total count
        query = f"""
            SELECT COUNT(*) FROM video_projects p WHERE {where_clause}
        """
        count_result = db.execute(text(query), params)
        total = count_result.scalar() or 0

        query = f"""
            SELECT
                p.id, p.title, p.source_type, p.status,
                p.target_duration_seconds, p.tags, p.category,
                p.created_at, p.updated_at,
                bt.name as template_name
            FROM video_projects p
            LEFT JOIN video_brand_templates bt ON bt.id = p.brand_template_id
            WHERE {where_clause}
            ORDER BY p.created_at DESC
            LIMIT :limit OFFSET :offset
        """
        results = db.execute(text(query), params).fetchall()

        return [self._row_to_dict(r) for r in results], total

    def update_project(
        self,
        db: Session,
        project_id: int,
        **updates
    ) -> Optional[Dict[str, Any]]:
        """Update a video project."""
        try:
            allowed_fields = {
                "title", "description", "source_text", "brand_template_id",
                "voice_profile_id", "target_duration_seconds", "target_formats",
                "generated_script", "generated_blog", "generated_podcast_notes",
                "hook_variants", "status", "error_message", "tags", "category"
            }

            set_clauses = []
            params = {"id": project_id}

            for key, value in updates.items():
                if key in allowed_fields:
                    if key in ["target_formats", "hook_variants", "tags"]:
                        value = json.dumps(value) if isinstance(value, list) else value
                    set_clauses.append(f"{key} = :{key}")
                    params[key] = value

            if not set_clauses:
                return self.get_project(db, project_id)

            set_clauses.append("updated_at = CURRENT_TIMESTAMP")

            query = f"""
                UPDATE video_projects
                SET {', '.join(set_clauses)}
                WHERE id = :id
            """
            db.execute(text(query), params)
            db.commit()

            return self.get_project(db, project_id)

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error updating video project: {e}")
            raise

    def delete_project(self, db: Session, project_id: int) -> bool:
        """Delete a video project (archive it)."""
        try:
            db.execute(text("""
                UPDATE video_projects
                SET status = 'archived', archived_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"id": project_id})
            db.commit()
            return True
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error deleting video project: {e}")
            return False

    # =========================================================================
    # CONTENT GENERATION
    # =========================================================================

    def generate_script(
        self,
        db: Session,
        project_id: int,
        thought: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate a video script from a thought/idea."""
        project = self.get_project(db, project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        source_text = thought or project.get("source_text", "")
        if not source_text:
            raise ValueError("No source text provided")

        target_duration = project.get("target_duration_seconds", 60)

        # Generate script using LLM
        script_prompt = self._build_script_prompt(
            source_text,
            target_duration,
            project.get("category", "mortgage")
        )

        generated_content = self._call_llm(script_prompt)

        # Parse the response to extract script and variants
        parsed = self._parse_script_response(generated_content)

        # Update project with generated content
        self.update_project(
            db,
            project_id,
            generated_script=parsed["script"],
            hook_variants=parsed["hooks"],
            status="draft"
        )

        return {
            "project_id": project_id,
            "script": parsed["script"],
            "hooks": parsed["hooks"],
            "estimated_duration_seconds": parsed.get("estimated_duration", target_duration),
            "word_count": len(parsed["script"].split())
        }

    def generate_blog_from_script(
        self,
        db: Session,
        project_id: int
    ) -> Dict[str, Any]:
        """Generate a blog post from the video script."""
        project = self.get_project(db, project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        script = project.get("generated_script")
        if not script:
            raise ValueError("No script available - generate script first")

        blog_prompt = self._build_blog_prompt(script, project.get("title", ""))

        blog_content = self._call_llm(blog_prompt)

        self.update_project(db, project_id, generated_blog=blog_content)

        return {
            "project_id": project_id,
            "blog": blog_content,
            "word_count": len(blog_content.split())
        }

    def generate_podcast_notes(
        self,
        db: Session,
        project_id: int
    ) -> Dict[str, Any]:
        """Generate podcast show notes from the video script."""
        project = self.get_project(db, project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        script = project.get("generated_script")
        if not script:
            raise ValueError("No script available - generate script first")

        podcast_prompt = self._build_podcast_prompt(script, project.get("title", ""))

        podcast_notes = self._call_llm(podcast_prompt)

        self.update_project(db, project_id, generated_podcast_notes=podcast_notes)

        return {
            "project_id": project_id,
            "podcast_notes": podcast_notes
        }

    # =========================================================================
    # STORYBOARD MANAGEMENT
    # =========================================================================

    def generate_storyboard(
        self,
        db: Session,
        project_id: int,
        visual_style: str = "modern"
    ) -> List[Dict[str, Any]]:
        """Generate storyboard scenes from the script."""
        project = self.get_project(db, project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        script = project.get("generated_script")
        if not script:
            raise ValueError("No script available - generate script first")

        target_duration = project.get("target_duration_seconds", 60)

        # Generate storyboard using LLM
        storyboard_prompt = self._build_storyboard_prompt(
            script, target_duration, visual_style
        )

        storyboard_content = self._call_llm(storyboard_prompt)
        scenes = self._parse_storyboard_response(storyboard_content)

        # Clear existing scenes and insert new ones
        db.execute(text("""
            DELETE FROM video_storyboard_scenes WHERE project_id = :id
        """), {"id": project_id})

        for i, scene in enumerate(scenes):
            db.execute(text("""
                INSERT INTO video_storyboard_scenes (
                    project_id, scene_index, duration_seconds,
                    voiceover_text, on_screen_text, visual_prompt,
                    visual_source, motion_style, scene_type,
                    created_at, updated_at
                ) VALUES (
                    :project_id, :index, :duration,
                    :voiceover, :on_screen, :visual_prompt,
                    :visual_source, :motion, :scene_type,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """), {
                "project_id": project_id,
                "index": i,
                "duration": scene.get("duration_seconds", 5),
                "voiceover": scene.get("voiceover_text", ""),
                "on_screen": scene.get("on_screen_text"),
                "visual_prompt": scene.get("visual_prompt"),
                "visual_source": scene.get("visual_source", "ai_image"),
                "motion": scene.get("motion_style", "ken_burns"),
                "scene_type": scene.get("scene_type", "content")
            })

        db.commit()

        return self.get_storyboard(db, project_id)

    def get_storyboard(self, db: Session, project_id: int) -> List[Dict[str, Any]]:
        """Get all storyboard scenes for a project."""
        results = db.execute(text("""
            SELECT * FROM video_storyboard_scenes
            WHERE project_id = :id
            ORDER BY scene_index
        """), {"id": project_id}).fetchall()

        return [self._row_to_dict(r) for r in results]

    def update_scene(
        self,
        db: Session,
        scene_id: int,
        **updates
    ) -> Optional[Dict[str, Any]]:
        """Update a storyboard scene."""
        try:
            allowed_fields = {
                "duration_seconds", "voiceover_text", "on_screen_text",
                "visual_prompt", "visual_url", "visual_source",
                "motion_style", "transition_in", "transition_out",
                "hook_text", "show_lower_third", "lower_third_text"
            }

            set_clauses = []
            params = {"id": scene_id}

            for key, value in updates.items():
                if key in allowed_fields:
                    set_clauses.append(f"{key} = :{key}")
                    params[key] = value

            if not set_clauses:
                return None

            set_clauses.append("updated_at = CURRENT_TIMESTAMP")

            query = f"""
                UPDATE video_storyboard_scenes
                SET {', '.join(set_clauses)}
                WHERE id = :id
            """
            db.execute(text(query), params)
            db.commit()

            result = db.execute(text("""
                SELECT * FROM video_storyboard_scenes WHERE id = :id
            """), {"id": scene_id}).fetchone()

            return self._row_to_dict(result) if result else None

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error updating scene: {e}")
            raise

    # =========================================================================
    # BRAND TEMPLATES
    # =========================================================================

    def get_brand_templates(
        self,
        db: Session,
        organization_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get available brand templates."""
        params = {}
        filters = ["is_active = true"]

        if organization_id:
            filters.append("(organization_id = :org_id OR organization_id IS NULL)")
            params["org_id"] = organization_id

        where_clause = " AND ".join(filters)

        query = f"""
            SELECT * FROM video_brand_templates
            WHERE {where_clause}
            ORDER BY is_default DESC, name
        """
        results = db.execute(text(query), params).fetchall()

        return [self._row_to_dict(r) for r in results]

    def create_brand_template(
        self,
        db: Session,
        organization_id: Optional[int],
        **template_data
    ) -> Dict[str, Any]:
        """Create a new brand template."""
        try:
            fields = [
                "organization_id", "name", "description",
                "primary_color", "secondary_color", "accent_color",
                "background_color", "text_color",
                "heading_font", "body_font", "caption_font",
                "logo_url", "watermark_url", "watermark_position",
                "caption_style", "nmls_number", "disclaimer_text"
            ]

            values = {f: template_data.get(f) for f in fields if f in template_data}
            values["organization_id"] = organization_id

            columns = ", ".join(values.keys())
            placeholders = ", ".join(f":{k}" for k in values.keys())

            query = f"""
                INSERT INTO video_brand_templates ({columns}, created_at, updated_at)
                VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
            """
            result = db.execute(text(query), values)

            template_id = result.fetchone()[0]
            db.commit()

            return self.get_brand_template(db, template_id)

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error creating brand template: {e}")
            raise

    def get_brand_template(self, db: Session, template_id: int) -> Optional[Dict[str, Any]]:
        """Get a brand template by ID."""
        result = db.execute(text("""
            SELECT * FROM video_brand_templates WHERE id = :id
        """), {"id": template_id}).fetchone()

        return self._row_to_dict(result) if result else None

    # =========================================================================
    # VOICE PROFILES
    # =========================================================================

    def get_voice_profiles(
        self,
        db: Session,
        organization_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get available voice profiles."""
        params = {}
        filters = ["is_active = true"]

        if organization_id:
            filters.append("(organization_id = :org_id OR organization_id IS NULL)")
            params["org_id"] = organization_id

        where_clause = " AND ".join(filters)

        query = f"""
            SELECT * FROM video_voice_profiles
            WHERE {where_clause}
            ORDER BY is_default DESC, name
        """
        results = db.execute(text(query), params).fetchall()

        return [self._row_to_dict(r) for r in results]

    def get_voice_profile(self, db: Session, profile_id: int) -> Optional[Dict[str, Any]]:
        """Get a voice profile by ID."""
        result = db.execute(text("""
            SELECT * FROM video_voice_profiles WHERE id = :id
        """), {"id": profile_id}).fetchone()

        return self._row_to_dict(result) if result else None

    def create_voice_profile(
        self,
        db: Session,
        organization_id: Optional[int],
        user_id: Optional[int] = None,
        **profile_data
    ) -> Dict[str, Any]:
        """Create a new voice profile."""
        try:
            result = db.execute(text("""
                INSERT INTO video_voice_profiles (
                    organization_id, user_id, name, description,
                    voice_engine, voice_id, language, speaking_rate, pitch,
                    is_active, created_at, updated_at
                ) VALUES (
                    :org_id, :user_id, :name, :description,
                    :voice_engine, :voice_id, :language, :speaking_rate, :pitch,
                    true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                ) RETURNING id
            """), {
                "org_id": organization_id,
                "user_id": user_id,
                "name": profile_data.get("name", "Custom Voice"),
                "description": profile_data.get("description"),
                "voice_engine": profile_data.get("voice_engine", "local_tts"),
                "voice_id": profile_data.get("voice_id"),
                "language": profile_data.get("language", "en-US"),
                "speaking_rate": profile_data.get("speaking_rate", 1.0),
                "pitch": profile_data.get("pitch", 1.0),
            })

            profile_id = result.fetchone()[0]
            db.commit()

            return self.get_voice_profile(db, profile_id)

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error creating voice profile: {e}")
            raise

    # Aliases for route compatibility
    def list_voice_profiles(self, db: Session, organization_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Alias for get_voice_profiles."""
        return self.get_voice_profiles(db, organization_id)

    def list_brand_templates(self, db: Session, organization_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Alias for get_brand_templates."""
        return self.get_brand_templates(db, organization_id)

    def get_storyboard_scenes(self, db: Session, project_id: int) -> List[Dict[str, Any]]:
        """Alias for get_storyboard."""
        return self.get_storyboard(db, project_id)

    def archive_project(self, db: Session, project_id: int) -> bool:
        """Alias for delete_project (which archives)."""
        return self.delete_project(db, project_id)

    def update_voice_profile(
        self,
        db: Session,
        profile_id: int,
        **updates
    ) -> Optional[Dict[str, Any]]:
        """Update a voice profile."""
        try:
            allowed_fields = {
                "name", "description", "voice_engine", "voice_id",
                "language", "speaking_rate", "pitch", "is_active"
            }

            set_clauses = []
            params = {"id": profile_id}

            for key, value in updates.items():
                if key in allowed_fields:
                    set_clauses.append(f"{key} = :{key}")
                    params[key] = value

            if not set_clauses:
                return self.get_voice_profile(db, profile_id)

            set_clauses.append("updated_at = CURRENT_TIMESTAMP")

            query = f"""
                UPDATE video_voice_profiles
                SET {', '.join(set_clauses)}
                WHERE id = :id
            """
            db.execute(text(query), params)
            db.commit()

            return self.get_voice_profile(db, profile_id)

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error updating voice profile: {e}")
            raise

    def delete_voice_profile(self, db: Session, profile_id: int) -> bool:
        """Deactivate a voice profile."""
        try:
            db.execute(text("""
                UPDATE video_voice_profiles
                SET is_active = false, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"id": profile_id})
            db.commit()
            return True
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error deleting voice profile: {e}")
            return False

    def create_scene(
        self,
        db: Session,
        project_id: int,
        **scene_data
    ) -> Dict[str, Any]:
        """Create a new storyboard scene."""
        try:
            # Get the next scene index
            result = db.execute(text("""
                SELECT COALESCE(MAX(scene_index), -1) + 1 as next_index
                FROM video_storyboard_scenes WHERE project_id = :id
            """), {"id": project_id}).fetchone()
            next_index = result[0] if result else 0

            result = db.execute(text("""
                INSERT INTO video_storyboard_scenes (
                    project_id, scene_index, duration_seconds,
                    voiceover_text, on_screen_text, visual_prompt,
                    visual_source, motion_style, scene_type,
                    created_at, updated_at
                ) VALUES (
                    :project_id, :index, :duration,
                    :voiceover, :on_screen, :visual_prompt,
                    :visual_source, :motion, :scene_type,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                RETURNING id
            """), {
                "project_id": project_id,
                "index": scene_data.get("scene_index", next_index),
                "duration": scene_data.get("duration_seconds", 5),
                "voiceover": scene_data.get("voiceover_text", ""),
                "on_screen": scene_data.get("on_screen_text"),
                "visual_prompt": scene_data.get("visual_prompt"),
                "visual_source": scene_data.get("visual_source", "ai_image"),
                "motion": scene_data.get("motion_style", "ken_burns"),
                "scene_type": scene_data.get("scene_type", "content")
            })

            scene_id = result.fetchone()[0]
            db.commit()

            scene = db.execute(text("""
                SELECT * FROM video_storyboard_scenes WHERE id = :id
            """), {"id": scene_id}).fetchone()

            return self._row_to_dict(scene)

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error creating scene: {e}")
            raise

    def delete_scene(self, db: Session, scene_id: int) -> bool:
        """Delete a storyboard scene."""
        try:
            # Get project_id and scene_index before deleting
            scene = db.execute(text("""
                SELECT project_id, scene_index FROM video_storyboard_scenes WHERE id = :id
            """), {"id": scene_id}).fetchone()

            if not scene:
                return False

            project_id, deleted_index = scene[0], scene[1]

            # Delete the scene
            db.execute(text("""
                DELETE FROM video_storyboard_scenes WHERE id = :id
            """), {"id": scene_id})

            # Re-index remaining scenes
            db.execute(text("""
                UPDATE video_storyboard_scenes
                SET scene_index = scene_index - 1
                WHERE project_id = :project_id AND scene_index > :deleted_index
            """), {"project_id": project_id, "deleted_index": deleted_index})

            db.commit()
            return True

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error deleting scene: {e}")
            return False

    def reorder_scenes(
        self,
        db: Session,
        project_id: int,
        scene_order: List[int]
    ) -> List[Dict[str, Any]]:
        """Reorder storyboard scenes."""
        try:
            for new_index, scene_id in enumerate(scene_order):
                db.execute(text("""
                    UPDATE video_storyboard_scenes
                    SET scene_index = :new_index, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :scene_id AND project_id = :project_id
                """), {
                    "new_index": new_index,
                    "scene_id": scene_id,
                    "project_id": project_id
                })

            db.commit()
            return self.get_storyboard(db, project_id)

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error reordering scenes: {e}")
            raise

    def generate_scene_visuals(
        self,
        db: Session,
        scene_id: int,
        style_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate AI visuals for a scene (placeholder for actual AI generation)."""
        scene = db.execute(text("""
            SELECT * FROM video_storyboard_scenes WHERE id = :id
        """), {"id": scene_id}).fetchone()

        if not scene:
            raise ValueError(f"Scene {scene_id} not found")

        scene_dict = self._row_to_dict(scene)

        # In production, this would call the AI image generation service
        # For now, return a placeholder
        visual_url = f"https://placeholder.com/video-scene/{scene_id}"

        # Update scene with generated visual
        db.execute(text("""
            UPDATE video_storyboard_scenes
            SET visual_url = :url, visual_source = 'ai_image', updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {"id": scene_id, "url": visual_url})
        db.commit()

        return {
            "scene_id": scene_id,
            "visual_url": visual_url,
            "visual_prompt": scene_dict.get("visual_prompt"),
            "status": "generated"
        }

    def update_brand_template(
        self,
        db: Session,
        template_id: int,
        **updates
    ) -> Optional[Dict[str, Any]]:
        """Update a brand template."""
        try:
            allowed_fields = {
                "name", "description", "primary_color", "secondary_color",
                "accent_color", "background_color", "text_color",
                "heading_font", "body_font", "caption_font",
                "logo_url", "watermark_url", "watermark_position",
                "caption_style", "nmls_number", "disclaimer_text", "show_disclaimer"
            }

            set_clauses = []
            params = {"id": template_id}

            for key, value in updates.items():
                if key in allowed_fields:
                    set_clauses.append(f"{key} = :{key}")
                    params[key] = value

            if not set_clauses:
                return self.get_brand_template(db, template_id)

            set_clauses.append("updated_at = CURRENT_TIMESTAMP")

            query = f"""
                UPDATE video_brand_templates
                SET {', '.join(set_clauses)}
                WHERE id = :id
            """
            db.execute(text(query), params)
            db.commit()

            return self.get_brand_template(db, template_id)

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error updating brand template: {e}")
            raise

    # =========================================================================
    # LLM INTEGRATION
    # =========================================================================

    def _call_llm(self, prompt: str) -> str:
        """Call the LLM for content generation."""
        try:
            if self.llm_provider == "anthropic" and self.anthropic_api_key:
                import anthropic
                client = anthropic.Anthropic(api_key=self.anthropic_api_key)

                response = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4096,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )

                return response.content[0].text

            else:
                # Fallback: return a template response
                logger.warning("No LLM provider configured, returning template")
                return self._get_template_response(prompt)

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return self._get_template_response(prompt)

    def _build_script_prompt(
        self,
        thought: str,
        duration_seconds: int,
        category: str
    ) -> str:
        """Build the prompt for script generation."""
        words_target = (duration_seconds / 60) * 150  # ~150 words per minute

        return f"""You are an expert video scriptwriter for mortgage and real estate professionals.

Create a compelling video script from this idea:

"{thought}"

Requirements:
- Target duration: {duration_seconds} seconds (~{int(words_target)} words)
- Category: {category}
- Format: Short-form social video (TikTok/Reels/Shorts style)
- Tone: Professional but approachable, builds trust

Structure your response as JSON:
{{
    "script": "The full script text here...",
    "hooks": [
        "Hook variant 1 (first 3 seconds)",
        "Hook variant 2",
        "Hook variant 3"
    ],
    "estimated_duration": {duration_seconds},
    "key_points": ["point 1", "point 2", "point 3"]
}}

Make the script:
1. Start with an attention-grabbing hook
2. Deliver value quickly
3. End with a clear call-to-action
4. Use conversational language
5. Include pauses for emphasis (marked with ...)

Return ONLY the JSON, no additional text."""

    def _build_blog_prompt(self, script: str, title: str) -> str:
        """Build prompt for blog generation from script."""
        return f"""Convert this video script into a blog post:

Title: {title}

Script:
{script}

Requirements:
- 500-800 words
- SEO-friendly structure with headings
- Include the key points from the script
- Add relevant context and detail
- Professional mortgage industry tone
- End with a call-to-action

Return only the blog post content in markdown format."""

    def _build_podcast_prompt(self, script: str, title: str) -> str:
        """Build prompt for podcast notes generation."""
        return f"""Create podcast show notes from this video script:

Title: {title}

Script:
{script}

Generate:
1. Episode summary (2-3 sentences)
2. Key takeaways (bullet points)
3. Timestamps outline
4. Resources mentioned
5. Call-to-action

Return in markdown format."""

    def _build_storyboard_prompt(
        self,
        script: str,
        duration: int,
        visual_style: str
    ) -> str:
        """Build prompt for storyboard generation."""
        return f"""Break this video script into scenes for a storyboard:

Script:
{script}

Total duration: {duration} seconds
Visual style: {visual_style}

For each scene, provide:
1. Duration in seconds
2. Voiceover text for that segment
3. On-screen text (if any)
4. Visual description/prompt for AI image generation
5. Motion style (static, pan_left, pan_right, zoom_in, zoom_out, ken_burns)
6. Scene type (hook, content, cta, transition)

Return as JSON array:
[
    {{
        "duration_seconds": 3,
        "voiceover_text": "Text spoken...",
        "on_screen_text": "Key words on screen",
        "visual_prompt": "Professional office setting with mortgage documents...",
        "motion_style": "zoom_in",
        "scene_type": "hook"
    }}
]

Return ONLY the JSON array."""

    def _strip_markdown_fences(self, response: str) -> str:
        """Strip markdown code fences from LLM response."""
        import re
        # Remove ```json ... ``` or ``` ... ``` blocks
        cleaned = response.strip()
        # Match ```json or ```JSON or just ```
        pattern = r'^```(?:json|JSON)?\s*\n?(.*?)\n?```$'
        match = re.match(pattern, cleaned, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Also try without newlines
        pattern2 = r'^```(?:json|JSON)?\s*(.*?)```$'
        match2 = re.match(pattern2, cleaned, re.DOTALL)
        if match2:
            return match2.group(1).strip()
        return cleaned

    def _parse_script_response(self, response: str) -> Dict[str, Any]:
        """Parse the LLM response for script generation."""
        try:
            # Strip markdown code fences if present
            cleaned = self._strip_markdown_fences(response)
            # Try to parse as JSON
            data = json.loads(cleaned)
            return {
                "script": data.get("script", response),
                "hooks": data.get("hooks", []),
                "estimated_duration": data.get("estimated_duration", 60)
            }
        except json.JSONDecodeError:
            # Return raw response as script
            return {
                "script": response,
                "hooks": [],
                "estimated_duration": 60
            }

    def _parse_storyboard_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse the LLM response for storyboard generation."""
        try:
            # Strip markdown code fences if present
            cleaned = self._strip_markdown_fences(response)
            # Try to parse as JSON
            scenes = json.loads(cleaned)
            if isinstance(scenes, list):
                return scenes
            return [scenes]
        except json.JSONDecodeError:
            # Create a single scene with the full content
            return [{
                "duration_seconds": 60,
                "voiceover_text": response,
                "visual_prompt": "Professional mortgage setting",
                "motion_style": "ken_burns",
                "scene_type": "content"
            }]

    def _get_template_response(self, prompt: str) -> str:
        """Get a template response when LLM is unavailable."""
        if "script" in prompt.lower():
            return json.dumps({
                "script": "Welcome to today's mortgage tip. [Your content here] Contact us to learn more about your home financing options.",
                "hooks": [
                    "Want to save thousands on your mortgage?",
                    "Here's what your lender won't tell you...",
                    "The secret to getting the best rate..."
                ],
                "estimated_duration": 60
            })
        elif "storyboard" in prompt.lower():
            return json.dumps([
                {
                    "duration_seconds": 3,
                    "voiceover_text": "Welcome to today's tip!",
                    "on_screen_text": "Mortgage Tips",
                    "visual_prompt": "Professional office with charts",
                    "motion_style": "zoom_in",
                    "scene_type": "hook"
                },
                {
                    "duration_seconds": 25,
                    "voiceover_text": "Here's what you need to know...",
                    "visual_prompt": "Home with family",
                    "motion_style": "ken_burns",
                    "scene_type": "content"
                },
                {
                    "duration_seconds": 5,
                    "voiceover_text": "Contact us today!",
                    "on_screen_text": "Book Your Consultation",
                    "visual_prompt": "Phone with calendar",
                    "motion_style": "zoom_out",
                    "scene_type": "cta"
                }
            ])
        return "Generated content placeholder"

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert a database row to a dictionary."""
        if row is None:
            return None

        if hasattr(row, '_mapping'):
            d = dict(row._mapping)
        elif hasattr(row, '_asdict'):
            d = row._asdict()
        else:
            d = dict(row)

        # Parse JSON fields
        json_fields = ['target_formats', 'hook_variants', 'tags', 'caption_words']
        for field in json_fields:
            if field in d and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass

        return d


# Global instance
video_project_service = VideoProjectService()
