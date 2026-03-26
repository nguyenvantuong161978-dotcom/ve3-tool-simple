"""
Psychology topic prompts - Tam ly / Giao duc.
Minh hoa cartoon minimalist: nhan vat dau tron trang, mat don gian,
silhouette people phu, visual metaphor manh, floating text labels,
diagrams, paper texture background. Style kenh giao duc YouTube.

Tham khao: Social_Media_Psychology_Video_Analysis.xlsx
"""


class PsychologyPrompts:
    """Prompts cho chu de Psychology / Education."""

    TOPIC_NAME = "psychology"
    TOPIC_LABEL = "Tam ly / Giao duc"

    # ========== FALLBACK & UTILITIES ==========
    def fallback_style(self) -> str:
        """Style suffix cho fallback prompts khi API fail."""
        return "Clean cartoon illustration, minimalist style, clean black outlines, paper texture background."

    def fallback_video_style(self) -> str:
        return "Smooth illustration animation, gentle movement"

    def split_scene_prompt(self, duration: float, min_shots: int, max_shots: int,
                           srt_start: str, srt_end: str, srt_text: str,
                           visual_moment: str, characters_used: str,
                           location_used: str, char_locks: list, loc_locks: list) -> str:
        """Prompt de chia scene dai thanh nhieu illustrations."""
        return f"""You are an ILLUSTRATOR for an educational YouTube channel. This scene is {duration:.1f} seconds - TOO LONG for one illustration (max 8s).
Split it into {min_shots}-{max_shots} DISTINCT illustration panels.

ORIGINAL SCENE:
- Duration: {duration:.1f}s (from {srt_start} to {srt_end})
- Narration: "{srt_text}"
- Visual concept: "{visual_moment}"
- Characters: {characters_used}
- Location: {location_used}

AVAILABLE CHARACTERS:
{chr(10).join(char_locks) if char_locks else 'None'}

AVAILABLE LOCATIONS:
{chr(10).join(loc_locks) if loc_locks else 'None'}

RULES FOR SPLITTING:
1. Each panel MUST be 3-8 seconds (divide the {duration:.1f}s total)
2. Each panel must show DIFFERENT aspect of the concept being explained
3. All panels together must cover the FULL narration
4. Use EXACT character/location IDs from the lists above
5. Use visual metaphors, floating text, diagrams to illustrate concepts

Examples of good splits:
- Concept explanation: Overview illustration -> Detail zoom -> Visual metaphor
- Comparison: Before state -> After state -> Resolution
- Emotional journey: Problem shown -> Impact felt -> Solution found

Return JSON only:
{{
    "shots": [
        {{
            "shot_number": 1,
            "duration": 5.0,
            "srt_text": "portion of narration for this panel",
            "visual_moment": "what the illustration shows - with visual metaphors",
            "shot_purpose": "why this illustration at this moment",
            "characters_used": "{characters_used}",
            "location_used": "{location_used}",
            "camera": "composition style"
        }}
    ]
}}"""

    def has_narrator_role(self) -> bool:
        """Psychology khong co narrator rieng."""
        return False

    # ========== STEP 1: Analyze Content ==========
    def step1_analyze(self, sampled_text: str) -> str:
        return f"""Analyze this educational/psychology content and extract key information for visual illustration.

NOTE: The content is provided in sampled format (beginning + middle + end) to capture the full narrative arc.

CONTENT (SAMPLED):
{sampled_text}

This is an EDUCATIONAL/PSYCHOLOGY video with CARTOON ILLUSTRATION style.
Analyze the content to understand:
- What psychological concept or life lesson is being taught?
- What emotions and situations are described?
- What visual metaphors can illustrate these concepts?
- What is the main character's journey/transformation?

The visual style uses:
- Cute minimalist character with round white head, simple dot eyes, gentle expressions
- Clean black outline illustration style
- Paper texture background
- Silhouette figures for other people
- Floating text labels and visual metaphors
- Warm, accessible, educational aesthetic

Return JSON only:
{{
    "setting": {{
        "era": "modern day",
        "location": "everyday life settings relevant to the content",
        "atmosphere": "warm, relatable, educational"
    }},
    "themes": ["theme1", "theme2", "theme3"],
    "visual_style": {{
        "cinematography": "minimalist cartoon illustration, clean black outlines, paper texture",
        "color_palette": "warm tones, soft pastels, clean whites",
        "lighting": "warm soft lighting, clean illustration lighting"
    }},
    "context_lock": "Cute minimalist cartoon illustration, clean black outline style, paper texture background, educational YouTube aesthetic"
}}
"""

    # ========== STEP 2: Segments ==========
    def step2_segments(self, context_lock: str, themes: list, total_duration: float,
                       total_srt: int, sampled_text: str) -> str:
        themes_str = ', '.join(themes) if themes else 'Not specified'
        return f"""Analyze this educational/psychology content and divide it into logical segments for video illustration.

IMPORTANT: Your segment analysis will be used by later steps to create CARTOON ILLUSTRATIONS with VISUAL METAPHORS.
Make your "message" and "key_elements" DETAILED enough to guide illustration creation.
Focus on: VISUAL METAPHORS, CONTRAST scenes, FLOATING TEXT ideas, DIAGRAM concepts.

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
2. key_elements: List of VISUAL elements (visual metaphors, floating text ideas, contrast situations, diagrams)
3. visual_summary: 2-3 sentences describing what CARTOON ILLUSTRATIONS should show, including visual metaphors
4. mood: The emotional tone (anxious, hopeful, sad, empowering, reflective, etc.)
5. characters_involved: Which people/roles appear (main character, silhouette people, etc.)

Return JSON only:
{{
    "segments": [
        {{
            "segment_id": 1,
            "segment_name": "Introduction/Hook",
            "message": "DETAILED description: what concept is introduced, what visual metaphor to use",
            "key_elements": ["contrast situation", "visual metaphor", "floating text idea", "character emotion"],
            "visual_summary": "2-3 sentences describing cartoon illustrations with visual metaphors",
            "mood": "reflective/anxious/hopeful/etc",
            "characters_involved": ["main character", "silhouette people"],
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
        return f"""Based on the content analysis below, identify the main character and any other characters for CARTOON ILLUSTRATION.

IMPORTANT VISUAL STYLE:
- This is a MINIMALIST CARTOON illustration style
- Main character: cute round white head, simple dot eyes, gentle expression, clean black outline
- The API must DECIDE the character's clothing and distinctive features based on the content
- Other people in scenes should be SIMPLE SILHOUETTE FIGURES (not detailed characters)
- Only create character entries for characters who need REFERENCE IMAGES (main character + any recurring named characters)

CONTENT CONTEXT:
- Setting: {setting.get('location', 'Not specified')}
- Visual style: {context_lock}

PEOPLE MENTIONED (from segments):
{chars_str}

CONTENT SEGMENTS ANALYSIS:
{segment_insights}

SAMPLE SRT CONTENT:
{targeted_srt_text[:8000] if targeted_srt_text else 'Use segment analysis above'}

CHARACTER DESIGN RULES:
- Main character: cute minimalist character with round white head, simple dot eyes, gentle expression, clean black outline illustration style
- Choose appropriate CLOTHING based on content theme (casual t-shirt, sweater, etc.)
- Choose appropriate ACCESSORIES or distinctive features (hair sprout, glasses, etc.)
- Other recurring named characters: same round head style but DIFFERENT clothing colors
- Background/crowd people: described as "simple silhouette people" in prompts (NO separate character entry needed)
- NO photorealistic portraits

For each character, provide:
1. portrait_prompt: Minimalist cartoon character on white background
2. character_lock: Full character description to be COPY-PASTED into every scene prompt
3. is_minor: true if character is a child

IMPORTANT: The character_lock must be COMPLETE and DETAILED enough to describe the character consistently across ALL scenes.
Example character_lock: "cute minimalist character with round white head, small green sprout on top, simple dot eyes, gentle expression, blue t-shirt, beige pants, white sneakers, clean black outline illustration style"

Return JSON:
{{
    "characters": [
        {{
            "id": "char_id",
            "name": "Name or Role",
            "role": "protagonist/supporting/narrator",
            "portrait_prompt": "Cute minimalist cartoon character, round white head, simple dot eyes, [expression], [distinctive feature], wearing [clothing], standing on pure white background, clean black outline illustration style",
            "character_lock": "cute minimalist character with round white head, [distinctive feature], simple dot eyes, [expression], [clothing details], clean black outline illustration style",
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
        return f"""Based on the content analysis below, identify all locations/settings for CARTOON ILLUSTRATION.

CONTENT CONTEXT:
- Setting: {setting.get('location', 'Not specified')}
- Visual style: {context_lock}

LOCATION HINTS (from segments):
{locs_str}

CONTENT SEGMENTS ANALYSIS:
{segment_insights}

SAMPLE SRT CONTENT:
{targeted_srt_text[:6000] if targeted_srt_text else 'Use segment analysis above'}

LOCATION ILLUSTRATION RULES:
- Clean minimalist cartoon/illustration style with clean black outlines
- Paper texture background feel
- Warm, accessible, everyday environments
- Simple but recognizable settings
- Focus on: key objects, atmosphere, spatial layout
- Locations MUST be EMPTY SPACES with NO characters/people/silhouettes
- NO photorealistic images

Return JSON only:
{{
    "locations": [
        {{
            "id": "loc_id",
            "name": "Location Name",
            "location_prompt": "Minimalist cartoon illustration of [location], [key objects and furniture], clean black outline style, warm atmosphere, paper texture background, no people, no characters",
            "location_lock": "cartoon [location] with [key feature], clean outline style (10-15 words)",
            "lighting_default": "warm soft lighting"
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

IMPORTANT: Each illustration will become a VIDEO CLIP. The visual must CLOSELY MATCH the narration content.
Think about: What VISUAL METAPHOR best illustrates this concept? What would make viewers UNDERSTAND the idea?

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

ILLUSTRATION TECHNIQUES TO USE:
- VISUAL METAPHORS: abstract concepts shown as physical objects (comparison as a scale, addiction as hooks, etc.)
- CONTRAST SCENES: split screen or before/after showing differences
- FLOATING TEXT LABELS: key words/phrases floating in scene to reinforce the message
- DIAGRAMS: brain diagrams, comparison charts, flow visualizations
- SILHOUETTE PEOPLE: background/crowd people as simple dark silhouettes
- CHARACTER EXPRESSIONS: exaggerated simple expressions to convey emotion

INSTRUCTIONS:
1. Create EXACTLY {image_count} illustration scenes - no more, no less
2. Each scene must VISUALLY REPRESENT the narration content
3. Use visual metaphors to illustrate abstract psychology concepts
4. Use EXACT character/location IDs from the lists above
5. scene_id: just use 1, 2, 3...
6. REFERENCES ACCURACY:
   - characters_used: ONLY main character or named characters who appear
   - location_used: ONLY ONE location per scene
   - For scenes with only silhouette people and no main character, leave characters_used EMPTY

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
            "visual_moment": "DETAILED description of what the illustration shows - include visual metaphors, floating text ideas, character actions",
            "characters_used": "nv_xxx",
            "location_used": "loc_xxx",
            "camera": "composition (centered, split screen, close-up, wide, etc.)",
            "lighting": "warm/soft/dramatic"
        }}
    ]
}}
Create exactly {image_count} illustrations!"""

    # ========== STEP 6: Scene Planning ==========
    def step6_scene_planning(self, context_lock: str, segments_info: str,
                              char_info: str, loc_info: str, scenes_text: str) -> str:
        return f"""You are an illustrator planning each scene's visual approach for an educational YouTube channel.

IMPORTANT: Each scene becomes a VIDEO CLIP. Plan visuals that CLOSELY MATCH the narration.

VISUAL STYLE: Minimalist cartoon illustration, clean black outlines, paper texture background.

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

For EACH scene, plan the cartoon illustration using these techniques:
1. artistic_intent: What concept/emotion to convey? What VISUAL METAPHOR to use?
2. shot_type: Composition (centered, split screen, triple panel, close-up, wide, bird's eye)
3. character_action: What is character doing? Expression? Include FLOATING TEXT labels if relevant
4. mood: Overall feeling (anxious, hopeful, lonely, empowered, reflective, etc.)
5. lighting: Warm soft / dramatic / contrast lighting
6. color_palette: Dominant colors for this specific scene
7. key_focus: What viewer should notice first (visual metaphor, character expression, floating text)

VISUAL TECHNIQUES TO CONSIDER:
- Split screen comparisons (real vs filtered, before vs after)
- Floating text labels ('MISSING OUT?', 'DESIGNED TO ADDICT', etc.)
- Visual metaphors (hooks for addiction, scales for comparison, walls vs boundaries)
- Silhouette crowds for "society" or "everyone else"
- Diagrams (brain, comparison charts, timelines)
- Transformation sequences (mask cracking, walls breaking, etc.)

Return JSON only:
{{
    "scene_plans": [
        {{
            "scene_id": 1,
            "artistic_intent": "Show contrast between everyone photographing food vs character just eating",
            "shot_type": "Wide restaurant table scene, centered composition",
            "character_action": "Character sits among silhouette people, calmly eating while others hold up phones",
            "mood": "Calm contrast, peaceful defiance",
            "lighting": "Warm restaurant lighting",
            "color_palette": "Warm earth tones, soft restaurant ambiance",
            "key_focus": "Contrast between phone users and character eating naturally"
        }}
    ]
}}
"""

    # ========== STEP 7: Scene Prompts ==========
    # ========== STEP 8: Thumbnail ==========
    def step8_thumbnail(self, setting: dict, themes: list, visual_style: dict,
                        context_lock: str, protagonist, chars_info: str,
                        locs_info: str, char_ids: list, loc_ids: list) -> str:
        return f"""You are a YouTube thumbnail designer for an EDUCATIONAL/PSYCHOLOGY channel.
Create 3 compelling thumbnail image prompts in CARTOON ILLUSTRATION style.

CONTENT CONTEXT:
- Setting: {setting}
- Themes: {themes}
- Visual style: {visual_style}
- Context lock: {context_lock}

MAIN CHARACTER: {protagonist.id} ({protagonist.name})
Character description: {protagonist.character_lock or protagonist.english_prompt}

ALL CHARACTERS:
{chars_info}

LOCATIONS:
{locs_info}

AVAILABLE REFERENCE IDs:
- Characters: {char_ids}
- Locations: {loc_ids}

VISUAL STYLE RULES:
- Clean minimalist cartoon illustration with clean black outlines
- Paper texture background
- Character must match the character_lock description exactly
- Use VISUAL METAPHORS and FLOATING TEXT to hook viewers
- NO photorealistic images

RULES FOR PROMPTS:
1. Write in English, cartoon illustration style
2. MUST annotate references EXACTLY like this:
   - Character: "cute character (nv1.png)" or "(nv1.png) looking up"
   - Location: "in cozy room (loc1.png)"
3. Include the FULL character description (from character_lock) in every prompt
4. Each prompt MUST be unique in composition and emotional appeal
5. End every prompt with: "clean black outline illustration style, paper texture background"

CREATE EXACTLY 3 THUMBNAIL PROMPTS:

VERSION 1 - "portrait_main" (CHARACTER CLOSE-UP):
Goal: Main character with strong expression that represents the video's core message.
Style: Close-up, character looking at viewer, visual metaphor element nearby, floating text with key concept.
Emotion: Curiosity, hope, determination.

VERSION 2 - "concept_visual" (VISUAL METAPHOR):
Goal: The most powerful visual metaphor from the content. Makes viewers think "I need to understand this!"
Style: Character interacting with visual metaphor (breaking chains, carrying weight, lighting candle in dark).
Emotion: Intrigue, realization, transformation.

VERSION 3 - "youtube_ctr" (MAXIMUM CLICK-THROUGH):
Goal: Maximum CTR using contrast/surprise. Character in unexpected situation with floating text hook.
Style: Split screen or dramatic contrast, character with big expressive eyes, bold floating text label.
Emotion: Surprise, "wait what?!", relatable struggle.

Return JSON only:
{{
  "thumbnails": [
    {{
      "thumb_id": 1,
      "version_desc": "portrait_main",
      "img_prompt": "...full prompt with (nvX.png) and (locX.png), ending with clean black outline illustration style, paper texture background",
      "characters_used": "nv1",
      "location_used": "loc1"
    }},
    {{
      "thumb_id": 2,
      "version_desc": "concept_visual",
      "img_prompt": "...",
      "characters_used": "nv1",
      "location_used": ""
    }},
    {{
      "thumb_id": 3,
      "version_desc": "youtube_ctr",
      "img_prompt": "...",
      "characters_used": "nv1",
      "location_used": ""
    }}
  ]
}}
"""

    # ========== STEP 7: Scene Prompts ==========
    def step7_scene_prompts(self, context_lock: str, scenes_text: str,
                             batch_size: int) -> str:
        return f"""Create detailed CARTOON ILLUSTRATION prompts for these {batch_size} scenes.

IMPORTANT: Each scene becomes a VIDEO CLIP. Prompts must create visuals that MATCH the narration closely.

VISUAL STYLE (MUST follow for ALL scenes):
{context_lock}

CRITICAL ILLUSTRATION STYLE RULES:
- Clean minimalist cartoon illustration with clean black outlines
- Paper texture background
- Main character: use the FULL character_lock description from reference
- Other people: "simple silhouette people" or "simple silhouette figures"
- Use VISUAL METAPHORS to illustrate abstract concepts
- Include FLOATING TEXT LABELS when the narration mentions key phrases/concepts
- Use SPLIT SCREEN for comparison scenes
- Use DIAGRAMS for scientific concepts
- NO photorealistic images - everything is minimalist cartoon illustration

REFERENCE FILE ANNOTATIONS:
- Main character MUST have reference file: "cute minimalist character (nv1.png)"
- Location MUST have reference file: "in cozy bedroom (loc_bedroom.png)"
- Character description from character_lock should be INCLUDED in the prompt
- Format: "[full character_lock description] (nv_xxx.png) [action] in [location description] (loc_xxx.png)"

SCENES TO PROCESS ({batch_size} scenes - create EXACTLY {batch_size} prompts):
{scenes_text}

CRITICAL REQUIREMENTS:
1. Create EXACTLY {batch_size} scene prompts
2. Each img_prompt MUST be UNIQUE and match the scene's narration
3. Include the FULL character description (from character_lock) in every prompt where character appears
4. Include visual metaphors, floating text labels, diagrams as planned
5. End every prompt with: "clean black outline illustration style, paper texture background"

For each scene, create:
1. img_prompt: Detailed illustration prompt matching the narration content
2. video_prompt: Animation description (character movement, text appearing, transitions)

Example img_prompt:
"Restaurant dining table scene, 4-5 simple silhouette people all holding up smartphones taking photos of food on table, cute minimalist character with round white head, small green sprout on top, simple dot eyes, gentle expression, blue t-shirt, beige pants, white sneakers, clean black outline illustration style (nv1.png) sitting among them HOLDING CHOPSTICKS actually eating food normally, warm restaurant lighting (loc_restaurant.png), contrast between phone users and real eater, clean black outline illustration style, paper texture background"

Example video_prompt:
"Multiple people simultaneously pull out smartphones and start photographing food, camera moves toward table, main character ignores phones picks up chopsticks and starts eating naturally, contrast visualization"

Return JSON only with EXACTLY {batch_size} scenes:
{{
    "scenes": [
        {{
            "scene_id": 1,
            "img_prompt": "DETAILED illustration prompt with character description (nv_xxx.png) and location (loc_xxx.png), visual metaphors, floating text, clean black outline illustration style, paper texture background",
            "video_prompt": "animation: character actions, text appearing/disappearing, visual transitions..."
        }}
    ]
}}
"""
