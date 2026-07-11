"""Static data: category guidance, character presets, background themes, art styles."""

CATEGORY_GUIDANCE = {
    "stoic":        "Draw from Stoic philosophy (Marcus Aurelius, Epictetus, Seneca). Use ancient wisdom applied to modern struggles. Themes: discipline, resilience, self-honesty, memento mori.",
    "motivation":   "Inspirational and empowering. Focus on overcoming adversity, taking action, breaking free from comfort zones. Raw and honest, not generic motivational cliches.",
    "meditation":   "Calm, reflective, mindful. Guide the viewer through inner awareness. Themes: stillness, presence, letting go, breath, acceptance.",
    "horror":       "Build dread slowly. Use suggestion over gore. The scariest thing is what you don't see. Themes: isolation, the unknown, things that feel wrong.",
    "love":         "Explore love in all forms — romantic, self-love, loss, longing. Honest and vulnerable, not cheesy. Show don't tell.",
    "psychology":   "Explore the human mind. Use psychological concepts made accessible. Themes: cognitive biases, behavior patterns, why we do what we do.",
    "history":      "Bring historical events or figures to life. Make the past feel present and relevant. Focus on the human story behind the facts.",
    "philosophy":   "Deep thinking made accessible. Explore big questions about existence, meaning, consciousness, morality. Challenge assumptions.",
    "nature":       "The beauty and power of the natural world. Themes: cycles of life, interconnection, wilderness, seasons, the small and the vast.",
    "scifi":        "Speculative and thought-provoking. Near-future scenarios, what-if questions, technology's impact on humanity.",
    "mystery":      "Unsolved puzzles, strange phenomena, things that don't add up. Build curiosity and suspense.",
    "life-lesson":  "Universal truths learned through experience. Practical wisdom. The kind of advice you wish someone told you earlier.",
    "dark":         "Explore the shadow side of human nature. Uncomfortable truths. Not nihilistic — honest.",
    "faith":        "Spiritual themes across traditions. Faith, doubt, surrender, grace, the sacred in the ordinary.",
    "money":        "Financial wisdom, wealth mindset, the relationship between money and happiness. Honest about both sides.",
    "relationship": "The dynamics between people. Communication, boundaries, attachment, growth. Real talk, not advice columns.",
}

CHARACTER_PRESETS = {
    "man": {
        "name": "Adult Man",
        "visual": "(man:1.4), male, medium build",
    },
    "woman": {
        "name": "Adult Woman",
        "visual": "(woman:1.4), female, graceful posture",
    },
    "elder": {
        "name": "Wise Elder",
        "visual": "(elderly man:1.4), gray hair, weathered face, wise expression, long simple robe",
    },
    "youth": {
        "name": "Young Person",
        "visual": "(young person:1.4), youthful face, casual clothing, curious expression",
    },
    "warrior": {
        "name": "Warrior",
        "visual": "(warrior:1.4), muscular build, battle-worn armor, scarred, determined expression",
    },
    "monk": {
        "name": "Monk",
        "visual": "(monk:1.4), shaved head, simple robes, calm serene expression, bare feet",
    },
    "child": {
        "name": "Child",
        "visual": "(child:1.4), small figure, innocent expression, simple clothing",
    },
    "silhouette": {
        "name": "Silhouette Figure",
        "visual": "(silhouette figure:1.4), dark outline, featureless, mysterious",
    },
    "stoic_calm": {
        "name": "Composed Stoic Figure",
        "visual": "(calm composed figure:1.4), modern or timeless clothing, relaxed grounded posture, serene unshaken expression, {action} pose, standing firm against {contrast_element}, steady breathing, quiet confidence, no fear in the face",
    },
    "stickman": {
        "name": "Expressive Webcomic Character",
        "visual": "(fleshed-out minimalist character:1.4), simple rounded body with visible limbs and hands (not thin stick lines), wearing hoodie and sneakers, {action} pose, {emotion} facial expression with clear eyebrows eyes and mouth, interacting with {object} rendered in matching line-art style and correct scale, highly expressive webcomic style, thick bold black outlines, flat black and white line art, no shading or greyscale fills, dynamic body language and exaggerated gesture, clear joints at shoulders elbows hips and knees, consistent proportions head roughly 1:5 of total body height, clean confident linework, single-panel webcomic illustration",
        "negative": "photograph, realistic anatomy, 3d render, full color, gradient shading, painting, messy scribble, thin uniform stick lines, blurry, low quality, distorted proportions, extra limbs, floating disconnected object, mismatched scale, stiff pose, blank expressionless face, cropped limbs",
    },
    "businessman": {
        "name": "Business Person",
        "visual": "(man in suit:1.4), professional attire, tie, briefcase, urban",
    },
    "artist": {
        "name": "Artist",
        "visual": "(artist:1.4), paint-stained clothes, creative expression, messy hair",
    },
    "samurai": {
        "name": "Samurai",
        "visual": "(samurai:1.4), traditional armor, katana at side, disciplined posture, topknot hair",
    },
    "philosopher": {
        "name": "Ancient Philosopher",
        "visual": "(philosopher:1.4), toga, sandals, long beard, contemplative expression, scroll in hand",
    },
    "traveler": {
        "name": "Lone Traveler",
        "visual": "(traveler:1.4), worn cloak, backpack, walking staff, weathered boots, distant gaze",
    },
    "robot": {
        "name": "Humanoid Robot",
        "visual": "(humanoid robot:1.4), sleek metal body, glowing eyes, mechanical joints, futuristic",
    },
    "girl": {
        "name": "Young Girl",
        "visual": "(young girl:1.4), long hair, simple dress, gentle expression, bare feet",
    },
    "comic_sketch_figure": {
        "name": "Comic Sketch Character",
        "visual": "(comic-style character:1.4), fleshed-out proportioned body with visible torso chest arms legs, not a thin stick figure, bold confident sketch linework, {action derived from narration}, {expression derived from narration — intensity should match the actual emotional weight of this specific line, not maximum expression by default}, hands with visible fingers positioned naturally for the action, interacting with (key story object:1.3) rendered in matching sketch style and correct scale, consistent head-to-body proportions across scenes",
    },
    "vector_cartoon_figure": {
        "name": "Bold Vector Cartoon Character",
        "visual": "(cartoon character:1.4), fleshed-out proportioned body with visible torso chest arms and legs, natural weight and volume, casual modern fashion with clean flat color blocking on clothing, thick bold black outlines around entire figure, {action derived from narration}, {expression derived from narration — subtle and true to this scene's actual emotional weight, not exaggerated by default}, hands with visible fingers positioned naturally for the action, interacting with (key story object:1.3) rendered in matching style and correct scale, consistent head-to-body proportions across scenes",
    },
    "vector_cartoon_figure_colorize": {
        "name": "Bold Vector Cartoon Character",
        "visual": "(cartoon character:1.4), fleshed-out proportioned body with visible torso chest arms and legs, natural weight and volume, full color casual modern fashion with flat solid color blocking on clothing (e.g. warm or cool solid colors like rust orange, teal, mustard, coral, navy chosen to fit the scene), thick bold black outlines around entire figure, {action derived from narration}, {expression derived from narration — subtle and true to this scene's actual emotional weight, not exaggerated by default}, hands with visible fingers positioned naturally for the action, interacting with (key story object:1.3) rendered in matching full-color style and correct scale, consistent head-to-body proportions and consistent color palette across scenes"
    },
}

BACKGROUND_THEMES = {
    "auto": {
        "name": "Auto (Script-Based)",
        "visual": "contextually appropriate background, dynamic environment matching the script narrative, scenery adapting to the main subject and action",
        "lighting": "dynamic lighting matching the scene's mood and context",
    },
    "nature":      {"name": "Nature & Wilderness",  "visual": "open natural landscape, rolling hills, trees, grass, vast sky",                                      "lighting": "natural golden hour light"},
    "urban":       {"name": "Urban City",            "visual": "city streets, buildings, concrete, modern architecture",                                             "lighting": "harsh streetlight, neon glow"},
    "forest":      {"name": "Deep Forest",           "visual": "dense forest, tall trees, filtered light through canopy, moss, ferns",                              "lighting": "dappled sunlight through leaves"},
    "ocean":       {"name": "Ocean & Coast",         "visual": "ocean waves, coastline, sandy beach, vast horizon",                                                 "lighting": "soft coastal light, sea mist"},
    "mountain":    {"name": "Mountains",             "visual": "mountain peaks, rocky terrain, valleys, snow-capped summits",                                       "lighting": "dramatic mountain light, clouds below"},
    "temple":      {"name": "Ancient Temple",        "visual": "stone ruins, ancient columns, sacred architecture, moss-covered walls",                             "lighting": "soft diffused light, dusty rays"},
    "desert":      {"name": "Desert",                "visual": "vast sand dunes, empty horizon, cracked earth, heat haze",                                          "lighting": "harsh overhead sun, long shadows"},
    "space":       {"name": "Cosmic Space",          "visual": "starfield, nebula, cosmic void, planets in distance",                                               "lighting": "ethereal glow, starlight"},
    "minimal":     {"name": "Minimalist",            "visual": "clean empty background, simple ground plane, negative space",                                       "lighting": "soft even studio light"},
    "rain":        {"name": "Rainy Atmosphere",      "visual": "rain falling, wet surfaces, reflections on ground, overcast sky",                                   "lighting": "dim diffused gray light, rain streaks"},
    "night":       {"name": "Night Scene",           "visual": "dark night sky, stars or moon, shadows, quiet darkness",                                            "lighting": "moonlight, dim blue tones"},
    "countryside": {"name": "Countryside",           "visual": "rolling fields, farmland, stone walls, dirt paths, wildflowers",                                    "lighting": "warm pastoral light"},
    "underwater":  {"name": "Underwater",            "visual": "deep ocean, coral, fish, light rays from surface, bubbles",                                         "lighting": "blue-green filtered light from above"},
    "ruins":       {"name": "Ancient Ruins",         "visual": "crumbling stone walls, overgrown vegetation, fallen pillars, forgotten civilization",               "lighting": "warm afternoon light through broken roof"},
    "library":     {"name": "Old Library",           "visual": "towering bookshelves, dusty books, reading desk, candlelight, wooden floor",                        "lighting": "warm candlelight, dust particles in air"},
    "battlefield": {"name": "Battlefield",           "visual": "scarred terrain, broken weapons, smoke, desolate field, dramatic sky",                              "lighting": "overcast stormy light, fire glow"},
    "greek":       {"name": "Ancient Greece",        "visual": "marble columns, Greek agora, olive trees, amphitheater, Parthenon-style architecture, Mediterranean hillside, terracotta rooftops, stone pathways", "lighting": "warm Mediterranean sunlight, golden afternoon glow"},
    "storm":       {"name": "Storm",                 "visual": "raging storm clouds, wind-driven rain, turbulent dark sky",                                         "lighting": "dim stormy light with a single beam breaking through"},
    "cliff":       {"name": "Cliff Edge",            "visual": "rocky cliff edge overlooking a vast drop, wind-swept grass",                                        "lighting": "soft dawn light, long shadows"},
    "garden":      {"name": "Garden",                "visual": "quiet walled garden, orderly rows, single tree in bloom",                                           "lighting": "warm late-afternoon light"},
    "cage":        {"name": "Cage / Prison",         "visual": "broken or open iron cage, chains lying loose on stone ground",                                      "lighting": "single shaft of light cutting through darkness"},
    "crowd":       {"name": "Crowd",                 "visual": "blurred indistinct crowd of figures in the background, faceless silhouettes",                       "lighting": "cool ambient light, subject slightly separated by warm light"},
    "hourglass":   {"name": "Hourglass / Time",      "visual": "large hourglass with falling sand, faded clock shapes in background",                              "lighting": "dim amber glow, dust particles in still air"},
    "path":        {"name": "Path / Journey",        "visual": "long winding path splitting into two directions, open field",                                       "lighting": "golden hour light, long stretched shadows"},
}

ART_STYLE_TEMPLATES = {
    "sketch":     "pencil sketch, black and white, cross hatching, fine line art",
    "watercolor": "watercolor painting, soft washes, flowing colors, paper texture",
    "cinematic":  "cinematic, dramatic lighting, highly detailed, vibrant colors",
    "anime":      "anime illustration, Studio Ghibli style, vibrant anime colors",
    "ghibli":     "Studio Ghibli style, Art by Hayao Miyazaki, hand drawn, cinematic, vivid colors, soft shading, playful",
    "oil":        "classical oil painting, rich colors, visible brushstrokes, canvas texture",
    "minimal":    "minimalist illustration, clean lines, simple shapes, negative space",
    "charcoal":   "charcoal drawing, dramatic shadows, smudged edges, high contrast",
    "stickfigure":"expressive fleshed-out webcomic character, thick bold black outlines on white background, flat black and white line art, dynamic pose",
    "realistic":  "photorealistic, ultra detailed, professional photography, sharp focus",
    "stoic_flat": "vibrant flat-design illustration, modern 2D animation style with ancient Stoic influence, muted warm color palette (terracotta, marble white, deep navy, muted gold), soft cel-shading for depth, soft dawn or dusk lighting, subtle atmospheric glow, clean vector shapes, polished professional illustration, philosophical explainer-video style, calm and contemplative mood",
}
