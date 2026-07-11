"""Art style definitions and category style mappings."""

ART_STYLES = {
    "pen": {
        "name": "Pen & Ink Drawing",
        "prompt": "black ink pen drawing on white paper, hand-drawn illustration, fine line art, crosshatching, sketch style, detailed pen strokes, artistic ink illustration, white background",
        "negative": "color, painting, photograph, digital art, 3d render, blurry",
    },
    "pencil": {
        "name": "Pencil Sketch",
        "prompt": "detailed pencil sketch on textured paper, graphite drawing, realistic shading, hand-drawn, artistic pencil illustration, soft shadows",
        "negative": "color, painting, photograph, digital art, 3d render",
    },
    "watercolor": {
        "name": "Watercolor Painting",
        "prompt": "beautiful watercolor painting, soft washes, flowing colors, wet-on-wet technique, artistic watercolor illustration, paper texture, delicate brushstrokes",
        "negative": "photograph, 3d render, digital art, sharp lines",
    },
    "anime": {
        "name": "Anime Style",
        "prompt": "anime illustration, Studio Ghibli style, beautiful anime art, detailed anime drawing, soft lighting, vibrant anime colors, high quality anime",
        "negative": "photograph, realistic, 3d render, western cartoon",
    },
    "ghibli": {
        "name": "Studio Ghibli",
        "prompt": "(Studio Ghibli style:1.3), anime illustration, hand drawn, full body character visible head to toe, naturalistic proportions with expressive large eyes and soft facial features, precise pose showing weight and intention body leaning or reaching or resting, nuanced facial expression eyes conveying warmth curiosity or melancholy, detailed clothing fabric folds cloth movement, lush organic environment wind-swept grass towering trees wooden structures sky clouds, warm ambient lighting golden hour or soft overcast, foreground midground background depth layering, painterly soft shading, cinematic wide composition, intricate scene details foliage water reflections dust motes, masterpiece, best quality, highly detailed",
        "negative": "ugly, deformed, noisy, blurry, low contrast, stiff pose, blank expression, missing limbs, floating figure, flat background, harsh lines, western cartoon, realistic photograph, 3d render, oversaturated, grimdark",
    },
    "cinematic": {
        "name": "Cinematic Digital Art",
        "prompt": "cinematic digital painting, dramatic lighting, highly detailed, vibrant colors, epic atmosphere, concept art, artstation trending, masterpiece",
        "negative": "blurry, low quality, deformed, ugly, sketch",
    },
    "oil": {
        "name": "Oil Painting",
        "prompt": "classical oil painting, rich colors, visible brushstrokes, museum quality, traditional art, canvas texture, Renaissance style lighting",
        "negative": "photograph, digital art, 3d render, cartoon, anime",
    },
    "comic": {
        "name": "Comic Book Style",
        "prompt": "comic book illustration, bold outlines, cel shading, dynamic composition, graphic novel art, vibrant comic colors, pop art",
        "negative": "photograph, realistic, 3d render, blurry",
    },
    "minimal": {
        "name": "Minimalist Art",
        "prompt": "minimalist illustration, clean lines, simple shapes, flat design, modern art, limited color palette, elegant simplicity, negative space",
        "negative": "complex, busy, realistic, photograph, detailed",
    },
    "pixel": {
        "name": "Pixel Art",
        "prompt": "pixel art illustration, retro game style, 16-bit aesthetic, pixelated, nostalgic, clean pixel work, vibrant pixel colors",
        "negative": "realistic, photograph, smooth, 3d render",
    },
    "charcoal": {
        "name": "Charcoal Drawing",
        "prompt": "charcoal drawing on paper, dramatic shadows, smudged edges, expressive strokes, artistic charcoal illustration, high contrast, moody atmosphere",
        "negative": "color, painting, photograph, digital art, clean lines",
    },
    "storybook": {
        "name": "Children's Storybook",
        "prompt": "children's book illustration, whimsical art style, soft pastel watercolor palette, warm golden lighting, rounded chunky character with full body visible head to toe, large expressive eyes conveying clear emotion, exaggerated playful pose arms wide or crouched or jumping, simple clothing with cute details buttons patches patterns, cozy inviting environment with recognizable props trees cottage mushrooms toys, storybook page composition with foreground midground depth, gentle soft shadows, fairy tale atmosphere, Beatrix Potter or Eric Carle inspired, masterpiece, best quality, highly detailed",
        "negative": "scary, dark, realistic, photograph, 3d render, stiff pose, blank expression, realistic proportions, thin limbs, missing face, floating figure, busy cluttered background, harsh shadows, muted colors, grotesque",
    },
    "adult_literary": {
        "name": "Prestige Literary",
        "prompt": "fine art book illustration, painterly texture, sophisticated muted limited palette, gallery-quality composition, precise character pose with weight and intention, expressive face with nuanced emotion subtle tension in brow and eyes, detailed hands gripping or gesturing meaningfully, environment elements grounding the figure in physical space, moody directional lighting casting soft shadows, contemplative introspective atmosphere, subtle visual symbolism layered into scene details, Edward Hopper or Kathe Kollwitz inspired, masterpiece, best quality, highly detailed",
        "negative": "garish, cartoonish, childish, oversaturated, simplistic, stiff pose, blank expression, flat lighting, missing hands, floating figure, stock photo composition, cheerful bright colors, anime, sketch, blurry",
    },
    "realistic": {
        "name": "Photorealistic",
        "prompt": "photorealistic, ultra detailed, professional photography, sharp focus, natural lighting, 8k resolution, stunning composition",
        "negative": "cartoon, anime, painting, drawing, sketch, abstract",
    },
    "stickfigure": {
        "name": "Expressive Character Study",
        "prompt": "expressive minimalist character illustration, bold thick black outlines on white background, simplified human figure with visible torso chest arms legs and head, chunky rounded limbs, proper head-body-limb proportions, full body visible from head to toe, dynamic exaggerated pose showing clear emotion through body language, tilted head leaning torso outstretched arms bent knees, large expressive face with thick eyebrows wide eyes open mouth, exaggerated facial features conveying strong emotion, visible clothing details hoodie jacket sneakers simple folds, scene-specific hand gestures and foot placement, flat black and white line art, webcomic illustration style, Scott Pilgrim style character, clean confident linework, no stray lines",
        "negative": "stick figure, single line limbs, wire frame body, no torso, missing body parts, headless, limbless, neutral expression, blank face, flat emotion, thin lines, crude doodle, realistic anatomy, photograph, 3d render, color, painting, shading, gradient, messy scratchy lines, floating body parts, disproportionate tiny head",
    },
    "sketch": {
        "name": "Pencil Sketch Drawing",
        "prompt": "Pencil Sketch Drawing, <lora:animeoutlineV4_16:1>, black and white drawing, graphite drawing, detailed pencil linework, expressive character pose, clear body language, precise facial expression, gestural hatching, fine texture detail, dynamic composition",
        "negative": "ugly, deformed, noisy, blurry, low contrast, color, painting, flat, stiff pose, neutral expression, faceless",
        "sd_override": {
            "steps": 8,
            "sampler_name": "DPM++ 2M",
            "scheduler": "Karras",
            "cfg_scale": 1.5,
        },
    },
    "stoic_flat": {
        "name": "Stoic Contemplative Illustration",
        "prompt": "vibrant flat-design illustration, modern 2D animation style with ancient Stoic influence, muted warm color palette terracotta marble white deep navy muted gold, soft cel-shading for depth, serene grounded human figure, calm unshaken expression, relaxed steady posture, soft dawn or dusk lighting, subtle atmospheric glow, clean vector shapes, painterly depth without noise, polished professional illustration, philosophical explainer-video style, calm contemplative mood, symbolic contrast between the composed figure and a turbulent environment",
        "negative": "stick figure, line art only, black and white, harsh neon colors, cartoonish exaggeration, photorealistic, 3d render, cluttered background, chaotic composition, blurry, low quality, distorted anatomy, extra limbs, cropped figure, glowing neon outlines, gritty horror tone",
    },
    "vibrant_flat": {
        "name": "Vibrant Explainer Illustration",
        "prompt": "vibrant flat-design illustration, modern 2D animation style, bold saturated color palette, soft cel-shading for depth, warm gradient background, expressive facial features, dynamic and energetic posture, clean vector shapes, subtle glow and light accents, polished professional illustration, trending explainer-video style, high visual appeal, crisp confident linework, sense of motion and momentum",
        "negative": "muted dull colors, flat lifeless expression, static rigid pose, photorealistic, 3d render, black and white, sketchy scribble lines, low contrast, cluttered background, distorted anatomy, extra limbs, cropped figure, gritty horror tone, washed out lighting",
    },
    "comic_sketch_style": {
        "name": "Comic Sketch Illustration",
        "prompt": "comic book illustration, confident ink linework with varied line weight, cross-hatching and hand-drawn sketch texture for shading and depth, black and white or limited two-tone color accent, panel-style composition, non-photorealistic hand-drawn feel, level of dynamism and motion lines should match the intensity of this specific scene — subtle and still for quiet or reflective moments, more energetic linework only when the narration calls for high action or high emotion",
        "negative": "photorealistic, 3d render, flat vector clip-art, minimalist thin stick lines, plain flat colors, no shading, no texture, exaggerated expression on every scene, forced dramatic pose regardless of content, blurry, distorted anatomy, extra limbs, cropped figure, muddy scribble, disproportionate tiny head",
    },
    "vector_cartoon_style": {
        "name": "Bold Vector Cartoon Illustration",
        "prompt": "bold vector cartoon illustration, thick confident black outlines, flat solid color blocking with no gradients, limited poster-style color palette, strong graphic silhouettes, clean geometric shapes, subtle flat shadow shapes used only to indicate depth not lighting mood, webtoon and graphic novel poster aesthetic, crisp confident linework, non-photorealistic, level of dynamism should match the intensity of this specific scene — subtle and grounded for quiet moments, bolder shapes and angles only when the narration calls for high action or high emotion",
        "negative": "photorealistic, 3d render, sketch texture, cross-hatching, pencil lines, soft gradients, airbrushed shading, watercolor texture, thin uniform stick lines, no body weight, exaggerated expression on every scene, forced dramatic pose regardless of content, blurry, distorted anatomy, extra limbs, cropped figure, muddy colors, washed out palette",
    },
    "vector_cartoon_style_collorize": {
        "name": "Bold Vector Cartoon Illustration",
        "prompt": "bold full-color vector cartoon illustration, thick confident black outlines, flat solid color blocking with no gradients, vivid poster-style color palette using warm and cool contrast (e.g. terracotta orange, deep teal, mustard yellow, soft coral, navy blue) chosen to match the scene's mood, strong graphic silhouettes, clean geometric shapes, subtle flat shadow shapes used only to indicate depth not lighting mood, webtoon and graphic novel poster aesthetic, crisp confident linework, non-photorealistic, level of dynamism should match the intensity of this specific scene — subtle and grounded for quiet moments, bolder shapes and angles only when the narration calls for high action or high emotion",
        "negative": "black and white, greyscale, monochrome, desaturated, photorealistic, 3d render, sketch texture, cross-hatching, pencil lines, soft gradients, airbrushed shading, watercolor texture, thin uniform stick lines, no body weight, exaggerated expression on every scene, forced dramatic pose regardless of content, blurry, distorted anatomy, extra limbs, cropped figure, muddy colors, washed out palette"
    },
}

CATEGORY_STYLES = {
    "meditation":   {"style": "watercolor", "mood": "serene peaceful calm spiritual"},
    "horror":       {"style": "charcoal",   "mood": "dark ominous terrifying shadowy"},
    "fantasy":      {"style": "cinematic",  "mood": "magical ethereal epic mystical"},
    "romance":      {"style": "watercolor", "mood": "warm intimate tender loving"},
    "motivational": {"style": "cinematic",  "mood": "powerful inspiring triumphant golden"},
    "history":      {"style": "oil",        "mood": "ancient grand historical dramatic"},
    "scifi":        {"style": "cinematic",  "mood": "futuristic neon technological cosmic"},
    "nature":       {"style": "watercolor", "mood": "natural organic peaceful lush"},
    "adventure":    {"style": "cinematic",  "mood": "epic vast adventurous dramatic"},
    "comedy":       {"style": "comic",      "mood": "funny playful bright cheerful"},
    "mystery":      {"style": "charcoal",   "mood": "mysterious dark foggy enigmatic"},
    "documentary":  {"style": "realistic",  "mood": "authentic real journalistic raw"},
    "fairytale":    {"style": "storybook",  "mood": "whimsical magical enchanted dreamy"},
    "gaming":       {"style": "pixel",      "mood": "retro nostalgic digital vibrant"},
    "zen":          {"style": "pen",        "mood": "minimal peaceful balanced harmonious"},
    "anime":        {"style": "anime",      "mood": "dynamic expressive vibrant emotional"},
}

ILLUSTRATION_STYLE_PROMPT = (
    "Digital illustration, cinematic lighting, highly detailed, "
    "vibrant colors, dramatic atmosphere, 9:16 portrait aspect ratio, "
    "storytelling scene, no text, no watermark"
)
