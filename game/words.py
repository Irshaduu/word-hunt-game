"""
Curated word list for Word Hunt.
100 common, recognizable English words (3-8 chars).
Easily expandable — just add more words to WORD_LIST.
"""

import random

WORD_LIST = [
    "the", "and", "for", "that", "this", "with", "you", "not", "are", "from",
    "your", "all", "have", "new", "more", "was", "will", "home", "can", "about",
    "page", "has", "search", "free", "but", "our", "one", "other", "time", "they",
    "site", "may", "what", "which", "their", "news", "out", "use", "any", "there",
    "see", "only", "his", "when", "contact", "here", "business", "who", "web", "also",
    "now", "help", "get", "view", "online", "first", "been", "would", "how", "were",
    "services", "some", "these", "click", "its", "like", "service", "than", "find", "price",
    "date", "back", "top", "people", "had", "list", "name", "just", "over", "state",
    "year", "day", "into", "email", "two", "health", "world", "next", "used", "work",
    "last", "most", "products", "music", "buy", "data", "make", "them", "should", "product",
    "system", "post", "her", "city", "add", "policy", "number", "such", "please", "support",
    "message", "after", "best", "software", "then", "jan", "good", "video", "well", "where",
    "info", "rights", "public", "books", "high", "school", "through", "each", "links", "she",
    "review", "years", "order", "very", "privacy", "book", "items", "company", "read", "group",
    "need", "many", "user", "said", "does", "set", "under", "general", "research", "january",
    "mail", "full", "map", "reviews", "program", "life", "know", "games", "way", "days",
    "part", "could", "great", "united", "hotel", "real", "item", "center", "ebay", "must",
    "store", "travel", "comments", "made", "report", "off", "member", "details", "line", "terms",
    "before", "hotels", "did", "send", "right", "type", "because", "local", "those", "using",
    "results", "office", "national", "car", "design", "take", "posted", "internet", "address", "within",
    "states", "area", "want", "phone", "dvd", "shipping", "reserved", "subject", "between", "forum",
    "family", "long", "based", "code", "show", "even", "black", "check", "special", "prices",
    "website", "index", "being", "women", "much", "sign", "file", "link", "open", "today",
    "south", "case", "project", "same", "pages", "version", "section", "own", "found", "sports",
    "house", "related", "security", "both", "county", "american", "photo", "game", "members", "power",
    "while", "care", "network", "down", "computer", "systems", "three", "total", "place", "end",
    "download", "him", "without", "per", "access", "think", "north", "current", "posts", "big",
    "media", "law", "control", "water", "history", "pictures", "size", "art", "personal", "since",
    "guide", "shop", "board", "location", "change", "white", "text", "small", "rating", "rate",
    "children", "during", "usa", "return", "students", "shopping", "account", "times", "sites", "level",
    "digital", "profile", "previous", "form", "events", "love", "old", "john", "main", "call",
    "hours", "image", "title", "non", "another", "why", "shall", "property", "class", "still",
    "money", "quality", "every", "listing", "content", "country", "private", "little", "visit", "save",
    "tools", "low", "reply", "customer", "december", "compare", "movies", "include", "college", "value",
    "article", "york", "man", "card", "jobs", "provide", "food", "source", "author", "press",
    "learn", "sale", "around", "print", "course", "job", "canada", "process", "teen", "room",
    "stock", "training", "too", "credit", "point", "join", "science", "men", "advanced", "west",
    "sales", "look", "english", "left", "team", "estate", "box", "select", "windows", "photos",
    "gay", "thread", "week", "category", "note", "live", "large", "gallery", "table", "register",
    "however", "june", "october", "november", "market", "library", "really", "action", "start", "series",
    "model", "features", "air", "industry", "plan", "human", "provided", "yes", "required", "second",
    "hot", "cost", "movie", "forums", "march", "better", "say", "july", "yahoo", "going",
    "medical", "test", "friend", "come", "dec", "server", "study", "cart", "staff", "articles",
    "san", "feedback", "again", "play", "looking", "issues", "april", "never", "users", "complete",
    "street", "topic", "comment", "things", "working", "against", "standard", "tax", "person", "below",
    "mobile", "less", "got", "blog", "party", "payment", "login", "student", "let", "programs",
    "offers", "legal", "above", "recent", "park", "stores", "side", "act", "problem", "red",
    "give", "memory", "social", "august", "quote", "language", "story", "sell", "options", "rates",
    "create", "key", "body", "young", "america", "field", "few", "east", "paper", "single",
    "age", "club", "example", "girls", "password", "latest", "road", "gift", "question", "changes",
    "night", "hard", "texas", "oct", "pay", "four", "poker", "status", "browse", "issue",
    "range", "building", "seller", "court", "february", "always", "result", "audio", "light", "write",
    "war", "nov", "offer", "blue", "groups", "easy", "given", "files", "event", "release",
    "analysis", "request", "fax", "china", "making", "picture", "needs", "possible", "might", "yet",
    "month", "major", "star", "areas", "future", "space", "hand", "sun", "cards", "problems",
    "london", "meeting", "rss", "become", "interest", "child", "keep", "enter", "share", "similar",
    "garden", "schools", "million", "added", "listed", "baby", "learning", "energy", "run", "delivery",
    "net", "popular", "term", "film", "stories", "put", "journal", "reports", "try", "welcome",
    "central", "images", "notice", "original", "head", "radio", "until", "cell", "color", "self",
    "council", "away", "includes", "track", "archive", "once", "others", "format", "least", "society",
    "months", "log", "safety", "friends", "sure", "faq", "trade", "edition", "cars", "messages",
    "tell", "further", "updated", "able", "having", "provides", "david", "fun", "already", "green",
    "studies", "close", "common", "drive", "specific", "several", "gold", "feb", "living", "sep",
    "called", "short", "arts", "lot", "ask", "display", "limited", "powered", "means", "director",
    "daily", "beach", "past", "natural", "whether", "due", "five", "upon", "period", "planning",
    "database", "says", "official", "weather", "mar", "land", "average", "done", "window", "france",
    "pro", "region", "island", "record", "direct", "records", "district", "calendar", "costs", "style",
    "url", "front", "update", "parts", "aug", "ever", "early", "miles", "sound", "resource",
    "present", "either", "ago", "document", "word", "works", "material", "bill", "apr", "written",
    "talk", "federal", "hosting", "rules", "final", "adult", "tickets", "thing", "centre", "via",
    "cheap", "kids", "finance", "true", "minutes", "else", "mark", "third", "rock", "gifts",
    "europe", "reading", "topics", "bad", "tips", "plus", "auto", "cover", "usually", "edit",
    "together", "videos", "percent", "fast", "function", "fact", "unit", "getting", "global", "tech",
    "meet", "far", "economic", "player", "projects", "lyrics", "often", "submit", "germany", "amount",
    "watch", "included", "feel", "though", "bank", "risk", "thanks", "deals", "various", "words",
    "linux", "jul", "james", "weight", "town", "heart", "received", "choose", "archives", "points",
    "magazine", "error", "camera", "jun", "girl", "toys", "clear", "golf", "receive", "domain",
    "methods", "chapter", "makes", "policies", "loan", "wide", "beauty", "manager", "india", "position",
    "taken", "sort", "listings", "models", "michael", "known", "half", "cases", "step", "florida",
    "simple", "quick", "none", "wireless", "license", "paul", "friday", "lake", "whole", "annual",
    "later", "basic", "sony", "shows", "google", "church", "method", "purchase", "active", "response",
    "practice", "hardware", "figure", "fire", "holiday", "chat", "enough", "designed", "along", "among",
    "death", "writing", "speed", "html", "loss", "face", "brand", "discount", "higher", "effects",
    "created", "remember", "oil", "bit", "yellow", "increase", "kingdom", "base", "near", "thought",
    "stuff", "french", "storage", "japan", "doing", "loans", "shoes", "entry", "stay", "nature",
    "orders", "africa", "summary", "turn", "mean", "growth", "notes", "agency", "king", "monday",
    "european", "activity", "copy", "although", "drug", "pics", "western", "income", "force", "cash",
    "overall", "bay", "river", "package", "contents", "seen", "players", "engine", "port", "album",
    "regional", "stop", "supplies", "started", "bar", "views", "plans", "double", "dog", "build",
    "screen", "exchange", "types", "soon", "lines", "continue", "across", "benefits", "needed", "season",
    "apply", "someone", "held", "anything", "printer", "believe", "effect", "asked", "eur", "mind",
    "sunday", "casino", "pdf", "lost", "tour", "menu", "volume", "cross", "anyone", "mortgage",
    "hope", "silver", "wish", "inside", "solution", "mature", "role", "rather", "weeks", "addition",
    "came", "supply", "nothing", "certain", "usr", "running", "lower", "union", "jewelry", "clothing",
    "mon", "com", "fine", "names", "robert", "homepage", "hour", "gas", "skills", "six",
    "bush", "islands", "advice", "career", "military", "rental", "decision", "leave", "british", "teens",
    "pre", "huge", "sat", "woman", "zip", "bid", "kind", "sellers", "middle", "move",
    "cable", "taking", "values", "division", "coming", "tuesday", "object", "lesbian", "machine", "logo",
    "length", "actually", "nice", "score", "client", "returns", "capital", "follow", "sample", "sent",
    "shown", "saturday", "england", "culture", "band", "flash", "lead", "george", "choice", "went",
    "starting", "fri", "thursday", "courses", "consumer", "airport", "foreign", "artist", "outside", "levels",
    "channel", "letter", "mode", "phones", "ideas", "fund", "summer", "allow", "degree", "contract",
    "button", "releases", "wed", "homes", "super", "male", "matter", "custom", "virginia", "almost",
    "took", "located", "multiple", "asian", "editor", "inn", "cause", "song", "cnet", "ltd",
    "los", "focus", "late", "fall", "featured", "idea", "rooms", "female", "inc", "win",
    "thomas", "primary", "cancer", "numbers", "reason", "tool", "browser", "spring", "answer", "voice",
    "friendly", "schedule", "purpose", "feature", "bed", "comes", "police", "everyone", "approach", "cameras",
    "brown", "physical", "hill", "maps", "medicine", "deal", "hold", "ratings", "chicago", "forms",
    "glass", "happy", "tue", "smith", "wanted", "thank", "safe", "unique", "survey", "prior",
    "sport", "ready", "feed", "animal", "sources", "mexico", "regular", "secure", "simply", "evidence",
    "station", "round", "paypal", "favorite", "option", "master", "valley", "recently", "probably", "thu",
    "rentals", "sea", "built", "blood", "cut", "improve", "hall", "larger", "anti", "networks",
    "earth", "parents", "nokia", "impact", "transfer", "kitchen", "strong", "tel", "carolina", "wedding",
    "hospital", "ground", "overview", "ship", "owners", "disease", "paid", "italy", "perfect", "hair",
    "kit", "classic", "basis", "command", "cities", "william", "express", "award", "distance", "tree",
    "peter", "ensure", "thus", "wall", "involved", "extra", "partners", "budget", "rated", "guides",
    "success", "maximum", "existing", "quite", "selected", "boy", "amazon", "patients", "warning", "wine",
    "horse", "vote", "forward", "flowers", "stars", "lists", "owner", "retail", "animals", "useful",
    "directly", "ways", "est", "son", "rule", "mac", "housing", "takes", "iii", "gmt",
    "bring", "catalog", "searches", "max", "trying", "mother", "told", "xml", "traffic", "joined",
    "input", "strategy", "feet", "agent", "valid", "bin", "modern", "senior", "ireland", "teaching",
    "door", "grand", "testing", "trial", "charge", "units", "instead", "canadian", "cool", "normal",
    "wrote", "ships", "entire", "leading", "metal", "positive", "fitness", "chinese", "opinion", "asia",
    "football", "abstract", "uses", "output", "funds", "greater", "likely", "develop", "artists", "java",
    "guest", "seems", "pass", "trust", "van", "contains", "session", "multi", "republic", "fees",
    "vacation", "century", "academic", "skin", "graphics", "indian", "prev", "ads", "mary", "expected",
    "ring", "grade", "dating", "pacific", "mountain", "pop", "filter", "mailing", "vehicle", "longer",
    "consider", "int", "northern", "behind", "panel", "floor", "german", "buying", "match", "proposed",
    "default", "require", "iraq", "boys", "outdoor", "deep", "morning", "allows", "rest", "protein",
    "plant", "reported", "hit", "pool", "mini", "politics", "partner", "authors", "boards", "faculty",
    "parties", "fish", "mission", "eye", "string", "sense", "modified", "pack", "released", "stage",
    "internal", "goods", "born", "unless", "richard", "detailed", "japanese", "race", "approved", "target",
    "except", "usb", "ability", "maybe", "moving", "brands", "places", "php", "pretty", "spain",
    "southern", "yourself", "etc", "winter", "battery", "youth", "pressure", "boston", "debt", "keywords",
    "medium", "core", "break", "purposes", "sets", "dance", "wood", "msn", "itself", "defined",
    "papers", "playing", "awards", "fee", "studio", "reader", "virtual", "device", "answers", "rent",
    "las", "remote", "dark", "external", "apple", "min", "offered", "theory", "enjoy", "remove",
    "aid", "surface", "minimum", "visual", "host", "variety", "teachers", "isbn", "martin", "manual",
    "block", "subjects", "agents", "repair", "fair", "civil", "steel", "songs", "fixed", "wrong",
    "hands", "finally", "updates", "desktop", "classes", "paris", "ohio", "gets", "sector", "capacity",
    "requires", "jersey", "fat", "fully", "father", "electric", "saw", "quotes", "officer", "driver",
    "dead", "respect", "unknown", "mike", "trip", "pst", "worth", "poor", "teacher", "eyes",
    "workers", "farm", "georgia", "peace", "campus", "tom", "showing", "creative", "coast", "benefit",
    "progress", "funding", "devices", "lord", "grant", "sub", "agree", "fiction", "hear", "watches",
    "careers", "beyond", "goes", "families", "led", "museum", "fan", "blogs", "wife", "accepted",
    "former", "ten", "hits", "zone", "complex", "cat", "die", "jack", "flat", "flow",
    "agencies", "parent", "spanish", "michigan", "columbia", "setting", "scale", "stand", "economy", "highest",
    "helpful", "monthly", "critical", "frame", "musical", "angeles", "path", "employee", "chief", "gives",
    "bottom", "packages", "detail", "laws", "changed", "pet", "heard", "begin", "colorado", "royal",
    "clean", "switch", "russian", "largest", "african", "guy", "titles", "relevant", "justice", "connect",
    "bible", "dev", "cup", "basket", "applied", "weekly", "vol", "demand", "suite", "vegas",
    "square", "chris", "advance", "skip", "diet", "army", "auction", "gear", "lee", "allowed",
    "correct", "charles", "nation", "selling", "lots", "piece", "sheet", "firm", "seven", "older",
    "illinois", "elements", "species", "jump", "cells", "module", "resort", "facility", "random", "pricing",
    "dvds", "minister", "motion", "looks", "fashion", "visitors", "monitor", "trading", "forest", "calls",
    "whose", "coverage", "couple", "giving", "chance", "vision", "ball", "ending", "clients", "actions",
    "listen", "discuss", "accept", "naked", "goal", "sold", "wind", "clinical", "sciences", "markets",
    "lowest", "highly", "appear", "lives", "currency", "leather", "palm", "patient", "actual", "stone",
    "bob", "commerce", "perhaps", "persons", "fit", "tests", "village", "accounts", "amateur", "met",
    "pain", "xbox", "factors", "coffee", "www", "settings", "buyer", "cultural", "steve", "easily",
    "oral", "ford", "poster", "edge", "root", "closed", "holidays", "ice", "pink", "zealand",
    "balance", "graduate", "replies", "shot", "initial", "label", "thinking", "scott", "llc", "sec",
    "canon", "league", "waste", "minute", "bus", "provider", "optional", "cold", "sections", "chair",
    "fishing", "effort", "phase", "fields", "bag", "fantasy", "letters", "motor", "context", "install",
    "shirt", "apparel", "foot", "mass", "crime", "count", "breast", "ibm", "johnson", "quickly",
    "dollars", "websites", "religion", "claim", "driving", "surgery", "patch", "heat", "wild", "measures",
    "kansas", "miss", "chemical", "doctor", "task", "reduce", "brought", "himself", "nor", "enable",
    "exercise", "bug", "santa", "mid", "leader", "diamond", "israel", "soft", "servers", "alone",
    "meetings", "seconds", "jones", "arizona", "keyword", "flight", "congress", "fuel", "username", "walk",
    "produced", "italian", "wait", "pocket", "saint", "rose", "freedom", "argument", "creating", "jim",
    "drugs", "joint", "premium", "fresh", "attorney", "upgrade", "factor", "growing", "stream", "pick",
    "hearing", "eastern", "auctions", "therapy", "entries", "dates", "signed", "upper", "serious", "prime",
    "samsung", "limit", "began", "louis", "steps", "errors", "shops", "del", "efforts", "informed",
    "thoughts", "creek", "worked", "quantity", "urban", "sorted", "myself", "tours", "platform", "load",
    "labor", "admin", "nursing", "defense", "machines", "tags", "heavy", "covered", "recovery", "joe",
    "guys", "merchant", "expert", "protect", "drop", "solid", "cds", "became", "orange", "vehicles",
    "prevent", "theme", "rich", "campaign", "marine", "guitar", "finding", "examples", "ipod", "saying",
    "spirit", "claims", "motorola", "seem", "affairs", "touch", "intended", "towards", "goals", "hire",
    "election", "suggest", "branch", "charges", "serve", "reasons", "magic", "mount", "smart", "talking",
    "gave", "ones", "latin", "avoid", "manage", "corner", "rank", "oregon", "element", "birth",
    "virus", "abuse", "requests", "separate", "quarter", "tables", "define", "racing", "facts", "kong",
    "column", "plants", "faith", "chain", "identify", "avenue", "missing", "died", "domestic", "sitemap",
    "moved", "houston", "reach", "mental", "viewed", "moment", "extended", "sequence", "inch", "attack",
    "sorry", "centers", "opening", "damage", "lab", "reserve", "recipes", "cvs", "gamma", "plastic",
    "produce", "snow", "placed", "truth", "counter", "failure", "follows", "weekend", "dollar", "camp",
    "ontario", "des", "films", "bridge", "native", "fill", "williams", "movement", "printing", "baseball",
    "owned", "approval", "draft", "chart", "played", "contacts", "jesus", "readers", "clubs", "lcd",
    "jackson", "equal", "matching", "offering", "shirts", "profit", "leaders", "posters", "variable", "ave",
    "expect", "parking", "compared", "workshop", "russia", "gone", "codes", "kinds", "seattle", "golden",
    "teams", "fort", "lighting", "senate", "forces", "funny", "brother", "gene", "turned", "portable",
    "tried", "disc", "returned", "pattern", "boat", "named", "theatre", "laser", "earlier", "sponsor",
    "icon", "warranty", "indiana", "harry", "objects", "ends", "delete", "evening", "assembly", "nuclear",
    "taxes", "mouse", "signal", "criminal", "issued", "brain", "sexual", "powerful", "dream", "obtained",
    "false", "cast", "flower", "felt", "passed", "supplied", "falls", "pic", "soul", "aids",
    "opinions", "promote", "stated", "stats", "hawaii", "appears", "carry", "flag", "decided", "covers",
    "hello", "designs", "maintain", "tourism", "priority", "adults", "clips", "savings", "graphic", "atom",
    "payments", "binding", "brief", "ended", "winning", "eight", "iron", "straight", "script", "served",
    "wants", "prepared", "void", "dining", "alert", "atlanta", "dakota", "tag", "mix", "disk",
    "queen", "vhs", "credits", "clearly", "fix", "handle", "sweet", "desk", "criteria", "pubmed",
    "dave", "diego", "hong", "vice", "truck", "behavior", "enlarge", "ray", "revenue", "measure",
    "milee", "poocha", "kamila", "chanie", "chettan", "chechi", "macha", "sushi", "kabar", "apa",
    "indomie", "dates", "ajwa", "nasi", "goreng", "hongkong", "crackers", "oioi", "shammi", "mallu",
    "akka", "oppa", "ikka", "kakka", "biriyani", "shawarma", "kundan", "kamu",
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


def get_random_board(n=71):
    """
    Generate a board of n random words.
    Uses an interlocking 4-3 row layout (brick pattern) to maximize space 
    efficiency, eliminate gaps, and prevent overlapping on mobile screens,
    while using jitter and shuffle to keep it looking chaotic.
    """
    words = random.sample(WORD_LIST, min(n, len(WORD_LIST)))

    # Calculate total rows needed for a 4-3 alternating grid
    pair_count = len(words) // 7
    remainder = len(words) % 7
    
    total_rows = pair_count * 2
    if remainder > 0:
        total_rows += 1
    if remainder > 4:
        total_rows += 1
        
    y_step = 90.0 / max(1, total_rows)
    
    positions = []
    row = 0
    words_placed = 0
    
    while words_placed < len(words):
        # Alternate between 4 columns and 3 columns to interlock the words
        if row % 2 == 0:
            centers_x = [18.0, 39.0, 61.0, 82.0]
        else:
            centers_x = [28.0, 50.0, 72.0]
            
        base_y = 5.0 + (row * y_step) + (y_step / 2.0)
        
        for base_x in centers_x:
            if words_placed >= len(words):
                break
                
            # Controlled jitter to make it look messy but safe from collisions
            jitter_x = random.uniform(-4.0, 4.0)
            jitter_y = random.uniform(-y_step * 0.3, y_step * 0.3)
            
            positions.append((base_x + jitter_x, base_y + jitter_y))
            words_placed += 1
            
        row += 1

    # Shuffle the positions so big/small words don't form predictable patterns
    random.shuffle(positions)

    board = []
    for i, word in enumerate(words):
        x, y = positions[i]
        
        board.append({
            "word": word,
            "fontSize": random.randint(14, 23),
            "color": random.choice(WORD_COLORS),
            "font": random.choice(WORD_FONTS),
            "rotation": random.randint(-25, 25),
            "x": round(x, 1),
            "y": round(y, 1),
        })

    return board

