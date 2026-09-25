"""
Mock AI Provider Implementation

Mock provider for testing and development purposes.
"""

import time
import random
from typing import Optional, List
from .base import (
    BaseAIProvider,
    AIProviderType,
    AIResponse,
    AIModelInfo,
    ModelCapability,
)


class MockProvider(BaseAIProvider):
    """Mock AI provider for testing"""

    def get_provider_type(self) -> AIProviderType:
        return AIProviderType.MOCK

    def _initialize_client(self):
        """Initialize mock client (no-op)"""
        self.client = None

    async def generate_text(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs,
    ) -> AIResponse:
        """Generate mock text response"""
        start_time = time.time()

        # Simulate processing time
        await self._simulate_processing_time()

        # Use default model if not specified
        if not model:
            model = self.get_default_model()

        # Generate mock content based on prompt length and type
        content = self._generate_mock_content(prompt, max_tokens or 4000)

        processing_time_ms = int((time.time() - start_time) * 1000)

        # Calculate mock usage metrics
        input_tokens = len(prompt.split()) * 1.3  # Approximate tokenization
        output_tokens = len(content.split()) * 1.3

        usage_metrics = self._calculate_usage_metrics(
            model=model,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            processing_time_ms=processing_time_ms,
        )

        return AIResponse(
            content=content,
            provider=self.provider_type.value,
            model=model,
            usage_metrics=usage_metrics,
            metadata={"mock_provider": True, "simulation_delay_ms": processing_time_ms},
            finish_reason="stop",
        )

    async def _simulate_processing_time(self):
        """Simulate realistic API response time"""
        import asyncio

        # Simulate 0.5-2 seconds processing time
        delay = random.uniform(0.5, 2.0)
        await asyncio.sleep(delay)

    def _generate_mock_content(self, prompt: str, max_tokens: int) -> str:
        """Generate mock content based on prompt"""
        prompt_lower = prompt.lower()

        # Detect transformation type from prompt
        if "blog post" in prompt_lower:
            return self._generate_blog_post_mock()
        elif "social media" in prompt_lower:
            return self._generate_social_media_mock()
        elif "email" in prompt_lower:
            return self._generate_email_mock()
        elif "newsletter" in prompt_lower:
            return self._generate_newsletter_mock()
        elif "summary" in prompt_lower:
            return self._generate_summary_mock()
        else:
            return self._generate_generic_mock()

    def _generate_blog_post_mock(self) -> str:
        """Generate mock blog post"""
        return """# The Power of AI-Driven Content Transformation

## Introduction

In today's digital landscape, content repurposing has become essential for maximizing reach and engagement. This comprehensive guide explores how AI can revolutionize your content strategy.

## Key Benefits

### 1. Time Efficiency
- Automate repetitive content creation tasks
- Focus on strategy and creative direction
- Scale content production effortlessly

### 2. Consistency
- Maintain brand voice across all platforms
- Ensure messaging alignment
- Reduce human error in content adaptation

### 3. Multi-Platform Optimization
- Tailor content for specific platforms
- Optimize for different audience preferences
- Maximize engagement potential

## Implementation Strategy

To successfully implement AI-driven content transformation:

1. **Audit existing content**
2. **Define transformation goals**
3. **Choose appropriate AI tools**
4. **Establish quality control processes**
5. **Monitor and optimize results**

## Conclusion

AI-powered content transformation represents the future of digital marketing. By embracing these technologies, businesses can achieve unprecedented efficiency and reach in their content strategies.

*Ready to transform your content strategy? Start your AI journey today.*"""

    def _generate_social_media_mock(self) -> str:
        """Generate mock social media posts"""
        return """🚀 Transform your content strategy with AI! 

✨ Key benefits:
• 10x faster content creation
• Consistent brand voice
• Multi-platform optimization

Ready to scale your content? Let's chat! 👇

#AI #ContentMarketing #DigitalTransformation #MarketingStrategy

---

📈 Content repurposing hack: Turn 1 blog post into 10+ pieces of content!

Blog → Twitter threads → LinkedIn posts → Instagram stories → Email sequences

Work smarter, not harder! 💪

#ContentHacks #MarketingTips #SocialMedia

---

🎯 Struggling with content consistency across platforms?

AI-powered transformation ensures:
✅ Brand voice alignment
✅ Platform-specific optimization  
✅ Audience engagement boost

Game-changer for modern marketers! 🔥

#AI #ContentStrategy #Marketing"""

    def _generate_email_mock(self) -> str:
        """Generate mock email sequence"""
        return """Subject: Welcome to the AI Content Revolution! 🚀

Hi there!

Welcome to our exclusive content transformation masterclass series. Over the next 5 days, you'll discover how AI can revolutionize your content strategy.

**What to expect:**
- Day 1: AI Content Basics (today!)
- Day 2: Platform-Specific Optimization
- Day 3: Brand Voice Consistency
- Day 4: Scaling Your Content
- Day 5: Advanced AI Strategies

Let's start with the fundamentals...

---

Subject: Day 2: Platform-Specific Content Magic ✨

Yesterday we covered the basics. Today, let's dive into platform optimization.

Each platform has unique characteristics:
• Twitter: Concise, engaging, hashtag-rich
• LinkedIn: Professional, value-driven, industry insights
• Instagram: Visual, story-driven, lifestyle-focused

The key? AI can automatically adapt your content for each platform while maintaining your core message.

Tomorrow: Maintaining brand voice consistency...

---

Subject: Your Content Transformation Journey Continues...

Hi again!

By now, you've learned the power of AI content transformation. Here's what successful users are achieving:

📊 Results from our community:
- 300% increase in content output
- 85% time savings
- 150% boost in engagement

Ready to implement these strategies? Reply and let me know your biggest content challenge!

Best regards,
The AI Content Team"""

    def _generate_newsletter_mock(self) -> str:
        """Generate mock newsletter"""
        return """# The AI Content Weekly 📰

*Your weekly dose of content transformation insights*

## This Week's Highlights

### 🚀 Feature Spotlight: Multi-Platform Magic
Our new AI transformation engine can now adapt content for 12+ platforms simultaneously. Users report 400% efficiency gains!

### 📈 Community Success Stories
"I transformed one webinar into 50 pieces of content in under 10 minutes!" - Sarah M., Marketing Director

### 🔧 Tool Update
New transformation types added:
- Podcast episode summaries
- Video script adaptations
- Interactive quiz content

## Industry Insights

The content marketing landscape is evolving rapidly. According to recent studies:
- 73% of marketers plan to increase AI usage
- Content repurposing ROI increased 250% this year
- Multi-platform strategies show 3x better engagement

## Quick Tips

💡 **This Week's Pro Tip:** Use AI to create content calendars. Input your key themes and let AI suggest optimal posting schedules across platforms.

🎯 **Community Question:** What's your biggest content challenge? Reply and we'll feature solutions in next week's newsletter!

## Upcoming Events

📅 **Webinar:** "Advanced AI Content Strategies" - Thursday 2PM EST
🎓 **Workshop:** "Platform Optimization Masterclass" - Next Tuesday

## Resources

- [Complete Guide to AI Content Transformation]
- [Platform-Specific Style Guides]
- [Content Calendar Templates]

---

*Happy transforming!*
The AI Content Team

P.S. Don't forget to connect with us on social media for daily tips and insights!"""

    def _generate_summary_mock(self) -> str:
        """Generate mock summary"""
        return """**Executive Summary: AI Content Transformation**

**Key Points:**
• AI-driven content repurposing increases efficiency by 300-500%
• Multi-platform optimization ensures consistent brand messaging
• Automated transformation reduces content creation time from hours to minutes
• Quality control mechanisms maintain human oversight and brand standards

**Benefits:**
- Scalable content production
- Improved ROI on content investments  
- Enhanced audience engagement across platforms
- Reduced manual workload for content teams

**Implementation Recommendations:**
1. Start with high-performing existing content
2. Define clear transformation guidelines
3. Implement quality review processes
4. Monitor performance metrics across platforms
5. Iterate and optimize based on results

**Expected Outcomes:**
Organizations implementing AI content transformation typically see 250-400% improvement in content output, 60-80% reduction in creation time, and 150-200% increase in cross-platform engagement within the first quarter.

**Next Steps:**
Begin with a pilot program focusing on blog-to-social-media transformations before expanding to additional content types and platforms."""

    def _generate_generic_mock(self) -> str:
        """Generate generic mock content"""
        return """**AI-Generated Content Transformation**

This is a mock response demonstrating the content transformation capabilities of our AI system. In a real scenario, this would contain:

✅ Professionally transformed content
✅ Platform-specific optimization
✅ Brand voice consistency
✅ Engagement-focused formatting

**Key Features:**
- Intelligent content adaptation
- Multi-format support
- Quality assurance protocols
- Performance optimization

The actual implementation would analyze your original content and transform it according to your specified requirements, maintaining quality while optimizing for your target platform and audience.

**Mock Provider Benefits:**
- Fast response times for testing
- Predictable output for development
- No API costs during development
- Consistent behavior for automated testing

This mock response helps developers and testers validate the system's functionality before integrating with live AI providers."""

    def get_available_models(self) -> List[AIModelInfo]:
        """Get mock models"""
        return [
            AIModelInfo(
                name="mock-gpt-4",
                display_name="Mock GPT-4",
                max_tokens=4096,
                cost_per_1k_input_tokens=0.0,  # No cost for mock
                cost_per_1k_output_tokens=0.0,
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CONVERSATION,
                    ModelCapability.CONTENT_CREATION,
                    ModelCapability.SUMMARIZATION,
                ],
                context_window=8192,
                supports_streaming=False,
                supports_function_calling=False,
            ),
            AIModelInfo(
                name="mock-claude",
                display_name="Mock Claude",
                max_tokens=4096,
                cost_per_1k_input_tokens=0.0,
                cost_per_1k_output_tokens=0.0,
                capabilities=[
                    ModelCapability.TEXT_GENERATION,
                    ModelCapability.CONVERSATION,
                    ModelCapability.CONTENT_CREATION,
                    ModelCapability.SUMMARIZATION,
                ],
                context_window=100000,
                supports_streaming=False,
                supports_function_calling=False,
            ),
        ]

    def get_default_model(self) -> str:
        """Get default mock model"""
        return "mock-gpt-4"

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Mock provider has no cost"""
        return 0.0

    async def validate_api_key(self) -> bool:
        """Mock provider always validates successfully"""
        return True
