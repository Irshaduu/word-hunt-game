"""
Curated word list for Word Hunt.
100 common, recognizable English words (3-8 chars).
Easily expandable — just add more words to WORD_LIST.
"""

import random

WORD_LIST = [
    "apple", "brave", "candy", "dance", "eagle",
    "flame", "grape", "honey", "ivory", "jewel",
    "knife", "lemon", "magic", "noble", "ocean",
    "piano", "queen", "river", "storm", "tiger",
    "ultra", "vivid", "waltz", "xenon", "yacht",
    "zebra", "arrow", "blaze", "charm", "dream",
    "ember", "frost", "ghost", "heart", "index",
    "jolly", "kayak", "lunar", "mango", "ninja",
    "orbit", "prism", "quilt", "robin", "solar",
    "torch", "unity", "vapor", "whale", "pixel",
    "bloom", "coral", "dusk", "echo", "fern",
    "globe", "haze", "iris", "jade", "kite",
    "lotus", "mist", "nest", "opal", "plum",
    "rain", "silk", "tide", "vine", "wind",
    "acorn", "birch", "cliff", "delta", "elk",
    "flint", "grain", "haven", "isle", "jazz",
    "kelp", "lily", "maple", "north", "olive",
    "pearl", "reef", "sage", "thorn", "umbra",
    "crown", "diver", "forge", "glyph", "hymn",
    "ingot", "joust", "knack", "lyric", "morph",
]

# Curated color palette for word display — vibrant, varied, readable on dark bg
WORD_COLORS = [
    "#FF6B9D", "#C084FC", "#67E8F9", "#FBBF24", "#34D399",
    "#FB7185", "#A78BFA", "#38BDF8", "#F59E0B", "#10B981",
    "#F472B6", "#818CF8", "#22D3EE", "#EAB308", "#6EE7B7",
    "#E879F9", "#6366F1", "#06B6D4", "#F97316", "#2DD4BF",
    "#FF8A80", "#B388FF", "#80D8FF", "#FFD180", "#A7FFEB",
]

# Fonts for word display — varied for visual chaos
WORD_FONTS = [
    "'Fredoka', cursive",
    "'Baloo 2', cursive",
    "'Bubblegum Sans', cursive",
    "'Chewy', cursive",
    "'Boogaloo', cursive",
    "'Righteous', cursive",
    "'Nunito', sans-serif",
]


def get_random_board(n=45):
    """
    Generate a board of n random words placed on a grid with jitter.
    Words get their own cell so they don't overlap, but random offsets
    within each cell keep the look scattered and chaotic.
    """
    words = random.sample(WORD_LIST, min(n, len(WORD_LIST)))

    # Calculate grid dimensions to fit n words
    cols = 5
    rows = (len(words) + cols - 1) // cols  # ceiling division

    # Cell size in percentage — tight packing
    cell_w = 92.0 / cols
    cell_h = 92.0 / rows

    # Create shuffled grid positions
    positions = []
    for r in range(rows):
        for c in range(cols):
            positions.append((r, c))
    random.shuffle(positions)

    board = []
    for i, word in enumerate(words):
        row, col = positions[i]

        # Base position for this cell
        base_x = 2 + col * cell_w
        base_y = 1 + row * cell_h

        # Random jitter within cell (up to 50% of cell size)
        jitter_x = random.uniform(0, cell_w * 0.45)
        jitter_y = random.uniform(0, cell_h * 0.35)

        board.append({
            "word": word,
            "fontSize": random.randint(15, 28),
            "color": random.choice(WORD_COLORS),
            "font": random.choice(WORD_FONTS),
            "rotation": random.randint(-18, 18),
            "x": round(base_x + jitter_x, 1),
            "y": round(base_y + jitter_y, 1),
        })

    return board
