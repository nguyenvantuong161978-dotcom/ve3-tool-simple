"""
Psychology topic prompts - Tam ly / Giao duc.
Anh minh hoa cartoon, nhan vat don gian (dau tron trang, ao len),
boi canh am cung, mau sac nhe nhang. Style kenh giao duc YouTube.
"""


class PsychologyPrompts:
    """Prompts cho chu de Psychology / Education."""

    TOPIC_NAME = "psychology"
    TOPIC_LABEL = "Tam ly / Giao duc"

    # Style chung cho moi prompt
    VISUAL_STYLE = (
        "Cute cartoon illustration style, simple character with white round head, "
        "spiky hair, expressive simple face (dot eyes, simple mouth), "
        "wearing green cable-knit sweater and khaki pants with white sneakers. "
        "Cozy warm indoor environments, soft pastel color palette, "
        "warm lighting from lamps, clean digital illustration, "
        "YouTube educational channel aesthetic, 16:9 aspect ratio"
    )

    # ========== STEP 1: Analyze Content ==========
    def step1_analyze(self, sampled_text: str) -> str:
        return f"""Analyze this educational/psychology content and extract key information for visual illustration.

NOTE: The content is provided in sampled format (beginning + middle + end) to capture the full narrative arc.

CONTENT (SAMPLED):
{sampled_text}

This is an EDUCATIONAL/PSYCHOLOGY video. Analyze the content to understand:
- What psychological concept or life lesson is being taught?
- What emotions and situations are described?
- What visual metaphors can illustrate these concepts?

Return JSON only:
{{
    "setting": {{
        "era": "modern day",
        "location": "everyday life settings (bedroom, living room, office, school, etc.)",
        "atmosphere": "warm, relatable, educational"
    }},
    "themes": ["theme1", "theme2", "theme3"],
    "visual_style": {{
        "cinematography": "cartoon illustration, simple character design, warm colors",
        "color_palette": "soft pastels, warm tones, cozy atmosphere",
        "lighting": "warm lamp light, soft natural light, comfortable indoor lighting"
    }},
    "context_lock": "Cute cartoon illustration of a simple white round-headed character in green sweater, warm cozy setting, educational YouTube style"
}}
"""

    # ========== STEP 2: Segments ==========
    def step2_segments(self, context_lock: str, themes: list, total_duration: float,
                       total_srt: int, sampled_text: str) -> str:
        themes_str = ', '.join(themes) if themes else 'Not specified'
        return f"""Analyze this educational/psychology content and divide it into logical segments for video illustration.

IMPORTANT: Your segment analysis will be used by later steps to create CARTOON ILLUSTRATIONS.
Make your "message" and "key_elements" DETAILED enough to guide illustration creation.
Focus on VISUAL METAPHORS and SITUATIONS that can be illustrated.

CONTENT CONTEXT:
{context_lock}

THEMES: {themes_str}

TOTAL DURATION: {total_duration:.1f} seconds
TOTAL SRT ENTRIES: {total_srt}

CONTENT (SAMPLED):
{sampled_text}

TASK: Divide the content into logical segments based on the psychological concepts or lesson structure.

CRITICAL REQUIREMENT:
- Your segments MUST cover ALL {total_srt} SRT entries
- First segment starts at srt_range_start: 1
- Last segment MUST end at srt_range_end: {total_srt}
- NO gaps between segments

For each segment, provide:
1. message: What concept/lesson is being taught? What situation is described?
2. key_elements: List of VISUAL elements that can be illustrated (emotions, situations, objects, metaphors)
3. visual_summary: 2-3 sentences describing what CARTOON ILLUSTRATIONS should show
4. mood: The emotional tone (anxious, hopeful, sad, empowering, reflective, etc.)
5. characters_involved: Which people/roles appear (protagonist, friend, family member, etc.)

Return JSON only:
{{
    "segments": [
        {{
            "segment_id": 1,
            "segment_name": "Introduction/Hook",
            "message": "DETAILED description: what concept is introduced, what situation is shown",
            "key_elements": ["character feeling emotion", "visual metaphor", "situation", "environment"],
            "visual_summary": "2-3 sentences describing cartoon illustrations for this segment",
            "mood": "reflective/anxious/hopeful/etc",
            "characters_involved": ["main character", "friend"],
            "estimated_duration": 15.0,
            "srt_range_start": 1,
            "srt_range_end": 25,
            "importance": "high/medium/low"
        }}
    ],
    "summary": "Brief overview of the educational content structure"
}}
"""

    # ========== STEP 3: Characters ==========
    def step3_characters(self, setting: dict, context_lock: str,
                         all_characters_mentioned: list, segment_insights: str,
                         targeted_srt_text: str) -> str:
        chars_str = ', '.join(all_characters_mentioned) if all_characters_mentioned else 'Analyze from content segments below'
        return f"""Based on the content analysis below, identify all characters/people and create CARTOON visual descriptions.

IMPORTANT: This is a CARTOON ILLUSTRATION style video. All characters should be simple cartoon characters
with white round heads, simple dot eyes, simple mouth expressions. They wear casual everyday clothing.

CONTENT CONTEXT (from Step 1):
- Setting: {setting.get('location', 'Not specified')}
- Visual style: {context_lock}

PEOPLE TO LOOK FOR (from segments):
{chars_str}

CONTENT SEGMENTS ANALYSIS:
{segment_insights}

SAMPLE SRT CONTENT:
{targeted_srt_text[:8000] if targeted_srt_text else 'Use segment analysis above'}

IMPORTANT CARTOON STYLE RULES:
- ALL characters have the SAME basic design: white round head, simple face (dot eyes, simple mouth)
- They are DIFFERENTIATED by: clothing color, hair style, accessories, height
- Main character: green cable-knit sweater, spiky white hair, khaki pants, white sneakers
- Other characters: different colored clothing to distinguish them
- NO photorealistic portraits - these are CARTOON characters

For each character, provide:
1. portrait_prompt: Cartoon character description (NOT photorealistic)
2. character_lock: Short 10-15 word cartoon description for scene prompts
3. is_minor: true if character is a child

Return JSON:
{{
    "characters": [
        {{
            "id": "char_id",
            "name": "Name or Role",
            "role": "protagonist/supporting/narrator",
            "portrait_prompt": "Cute cartoon character, white round head, simple dot eyes, [expression], [hair style], wearing [colored clothing], standing on pure white background, clean digital illustration, simple design",
            "character_lock": "cartoon character with white round head, [hair], wearing [colored clothing]",
            "is_minor": false
        }}
    ]
}}
"""

    # ========== STEP 4: Locations ==========
    def step4_locations(self, setting: dict, context_lock: str, char_names: list,
                        all_locations_hints: list, segment_insights: str,
                        targeted_srt_text: str) -> str:
        locs_str = ', '.join(all_locations_hints) if all_locations_hints else 'Analyze from content segments below'
        return f"""Based on the content analysis below, identify all locations/settings and create CARTOON ILLUSTRATION descriptions.

CONTENT CONTEXT (from Step 1):
- Setting: {setting.get('location', 'Not specified')}
- Visual style: {context_lock}

LOCATION HINTS (from segments):
{locs_str}

CONTENT SEGMENTS ANALYSIS:
{segment_insights}

SAMPLE SRT CONTENT:
{targeted_srt_text[:6000] if targeted_srt_text else 'Use segment analysis above'}

IMPORTANT CARTOON STYLE RULES:
- Locations should be CARTOON/ILLUSTRATION style, NOT photorealistic
- Cozy, warm environments with soft colors
- Warm lighting from lamps, windows, soft ambient light
- Clean digital illustration style
- Common settings: bedroom, living room, office, school, cafe, park
- Furniture and objects should look cartoon/illustrated

For each location, provide:
1. location_prompt: Cartoon illustration description for generating reference image
2. location_lock: Short description for scene prompts

RULES FOR LOCATION IMAGES:
- Locations MUST be EMPTY SPACES with NO characters/people
- Show: cartoon furniture, warm lighting, cozy atmosphere, everyday objects
- Style: clean digital illustration, warm color palette, soft shadows

Return JSON only:
{{
    "locations": [
        {{
            "id": "loc_id",
            "name": "Location Name",
            "location_prompt": "Cartoon illustration of [location], warm cozy atmosphere, soft lamp light, [furniture/objects], clean digital art, pastel colors, no people",
            "location_lock": "cartoon cozy [location] with warm lighting (10-15 words)",
            "lighting_default": "warm lamp light / soft natural light"
        }}
    ]
}}
"""

    # ========== STEP 5: Director Plan ==========
    def step5_director_plan(self, image_count: int, seg_name: str, message: str,
                            seg_duration: float, scene_duration: float,
                            min_scene_duration: int, max_scene_duration: int,
                            context_lock: str, char_locks: list, loc_locks: list,
                            srt_text: str) -> str:
        return f"""You are an ILLUSTRATOR for an educational YouTube channel. Create exactly {image_count} illustration scenes for this content segment.

SEGMENT INFO:
- Name: "{seg_name}"
- Message: "{message}"
- Duration: {seg_duration:.1f} seconds total
- Required: EXACTLY {image_count} illustrations
- Each illustration covers {min_scene_duration}-{max_scene_duration} seconds of narration

VISUAL STYLE:
{context_lock}

CHARACTERS (cartoon style):
{chr(10).join(char_locks) if char_locks else 'No characters defined'}

LOCATIONS (cartoon style):
{chr(10).join(loc_locks) if loc_locks else 'No locations defined'}

SRT CONTENT FOR THIS SEGMENT:
{srt_text}

INSTRUCTIONS:
1. Create EXACTLY {image_count} illustration scenes - no more, no less
2. Each scene = one cartoon illustration that VISUALIZES the concept being discussed
3. Think about VISUAL METAPHORS: how can you illustrate abstract psychology concepts?
4. Show characters in RELATABLE SITUATIONS (lying in bed, talking on phone, sitting alone, etc.)
5. Use EXACT character/location IDs from the lists above
6. scene_id: just use 1, 2, 3... (will be renumbered later)
7. REFERENCES ACCURACY:
   - characters_used: ONLY characters who appear in that illustration
   - location_used: ONLY ONE location per scene

Return JSON only:
{{
    "scenes": [
        {{
            "scene_id": 1,
            "srt_indices": [list of SRT indices covered],
            "srt_start": "timestamp",
            "srt_end": "timestamp",
            "duration": {scene_duration:.1f},
            "srt_text": "narration text for this scene",
            "visual_moment": "what the cartoon illustration shows - specific situation/metaphor",
            "characters_used": "nv_xxx, nv_yyy",
            "location_used": "loc_xxx",
            "camera": "composition (centered, side view, bird's eye, etc.)",
            "lighting": "warm/soft/dramatic"
        }}
    ]
}}
Create exactly {image_count} illustrations!"""

    # ========== STEP 6: Scene Planning ==========
    def step6_scene_planning(self, context_lock: str, segments_info: str,
                              char_info: str, loc_info: str, scenes_text: str) -> str:
        return f"""You are an illustrator planning each scene's visual approach for an educational YouTube channel.

VISUAL STYLE: Cartoon illustration with simple round-headed characters, warm cozy settings.

CONTENT CONTEXT:
{context_lock}

CONTENT SEGMENTS:
{segments_info if segments_info else 'Not specified'}

CHARACTERS (cartoon):
{char_info if char_info else 'Not specified'}

LOCATIONS (cartoon):
{loc_info if loc_info else 'Not specified'}

SCENES TO PLAN:
{scenes_text}

For EACH scene, plan the cartoon illustration:
1. artistic_intent: What concept/emotion should this illustration convey?
2. shot_type: Composition style (full scene, close-up on character, wide establishing shot, etc.)
3. character_action: What is the cartoon character doing? Expression? Body language?
4. mood: Overall feeling (anxious, hopeful, lonely, empowered, reflective, etc.)
5. lighting: Type of lighting (warm lamp, soft window light, dim evening, bright morning)
6. color_palette: Dominant colors (warm pastels, cool blues, muted earth tones, etc.)
7. key_focus: What should viewer notice first? (character's expression, visual metaphor, environment)

Return JSON only:
{{
    "scene_plans": [
        {{
            "scene_id": 1,
            "artistic_intent": "Show the character feeling overwhelmed by phone calls from family",
            "shot_type": "Full body centered composition",
            "character_action": "Standing in living room surrounded by floating phones, looking stressed",
            "mood": "Overwhelmed, anxious",
            "lighting": "Warm dim lamp light, evening atmosphere",
            "color_palette": "Warm earth tones, soft orange from lamp, muted blues",
            "key_focus": "Character's worried expression and the multiple phones around them"
        }}
    ]
}}
"""

    # ========== STEP 7: Scene Prompts ==========
    def step7_scene_prompts(self, context_lock: str, scenes_text: str,
                             batch_size: int) -> str:
        return f"""Create detailed CARTOON ILLUSTRATION prompts for these {batch_size} scenes.

VISUAL STYLE (MUST follow):
{context_lock}

IMPORTANT STYLE RULES:
- ALL illustrations must be in CARTOON/DIGITAL ILLUSTRATION style
- Characters have white round heads, simple dot eyes, simple mouth expressions
- Main character wears green cable-knit sweater, khaki pants, white sneakers
- Environments are cozy, warm, with soft pastel colors
- Clean lines, soft shadows, warm lighting
- YouTube educational channel aesthetic
- NO photorealistic images - everything is cartoon/illustration

REFERENCE FILE ANNOTATIONS:
- Each character who appears MUST have their reference file: "character (nv1.png)"
- Location MUST have reference file: "in the room (loc1.png)"
- Format: "Cartoon illustration of character (nv_xxx.png) doing action in location (loc_xxx.png)"

SCENES TO PROCESS ({batch_size} scenes - create EXACTLY {batch_size} prompts):
{scenes_text}

CRITICAL REQUIREMENTS:
1. Create EXACTLY {batch_size} illustration prompts
2. Each img_prompt MUST be UNIQUE
3. Each prompt MUST specify "cartoon illustration" or "digital illustration" style
4. Include character expressions and body language
5. Include environment details (furniture, lighting, objects)

For each scene, create:
1. img_prompt: Cartoon illustration prompt with reference annotations
2. video_prompt: Simple animation description (character moves, expression changes)

Example img_prompt:
"Cute cartoon illustration, a simple character with white round head and worried expression (nv1.png) lying on bed looking at phone, cozy bedroom with warm lamp light (loc_bedroom.png), soft pastel colors, clean digital art style, educational YouTube aesthetic"

Return JSON only with EXACTLY {batch_size} scenes:
{{
    "scenes": [
        {{
            "scene_id": 1,
            "img_prompt": "Cartoon illustration of character (nv_xxx.png) in situation, in location (loc_xxx.png), warm cozy style...",
            "video_prompt": "character slowly looks up, expression changes from sad to hopeful..."
        }}
    ]
}}
"""
