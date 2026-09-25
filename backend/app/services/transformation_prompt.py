"""
Transformation prompt builder — shared between the sync route and the Celery task.
Generates the user prompt for the AI provider based on transformation type + parameters.
"""

from typing import Dict, Any
from app.models.transformation import TransformationType

CONTENT_REPURPOSE_SYSTEM_PROMPT = (
    "You are an expert content strategist and writer. "
    "Transform the provided content into the requested format while preserving the key information "
    "and adapting the style appropriately. "
    "Output only the transformed content — no meta-commentary, no 'Here is your...' preamble."
)


def get_transformation_prompt(
    transformation_type: TransformationType,
    document_content: str,
    parameters: Dict[str, Any],
) -> str:
    """Build the user prompt for a transformation request."""
    base = f"Here is the original content:\n\n{document_content}\n\n"

    if transformation_type == TransformationType.BLOG_POST:
        p = base + "Transform this content into a well-structured blog post. "
        if "word_count" in parameters:
            p += f"Target word count: ~{parameters['word_count']} words. "
        if "tone" in parameters:
            p += f"Use a {parameters['tone']} tone. "
        p += "Include a compelling title, introduction, main sections with subheadings, and a conclusion."

    elif transformation_type == TransformationType.SOCIAL_MEDIA:
        platform = parameters.get("platform", "general social media")
        p = base + f"Create social media content for {platform} based on this. "
        count = parameters.get("post_count")
        if count:
            p += f"Generate {count} distinct posts. "
        p += "Each post should be engaging, concise, and include relevant hashtags."

    elif transformation_type == TransformationType.EMAIL_SEQUENCE:
        p = base + "Transform this content into an email sequence. "
        count = parameters.get("email_count", 3)
        p += f"Create a series of {count} emails. "
        p += (
            "Each email needs: a subject line, an engaging opening, valuable body content, "
            "and a clear call-to-action. Format as Email 1, Email 2, etc."
        )

    elif transformation_type == TransformationType.NEWSLETTER:
        p = base + "Convert this content into a newsletter. "
        sections = parameters.get("sections")
        if sections:
            p += f"Include these sections: {', '.join(sections)}. "
        p += "Use a clear structure with an engaging intro, main content sections, and a closing with next steps."

    elif transformation_type == TransformationType.SUMMARY:
        p = base + "Create a concise summary of this content. "
        length = parameters.get("length")
        if length:
            p += f"Aim for approximately {length} words. "
        p += "Capture the key points, main arguments, and essential information."

    else:  # CUSTOM or fallback
        custom_instructions = parameters.get(
            "custom_instructions",
            "Transform this content into a new format while preserving the key information.",
        )
        p = base + custom_instructions

    return p
