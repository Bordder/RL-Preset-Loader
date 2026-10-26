"""Where things are on screen, as fractions of the game picture (0..1), so any 16:9 resolution works.

Measured from the user's 1440p English screenshots in reference/screenshots/.
"""

# Region the menus live in (left side of the screen). Reading less of the screen is faster.
MENU_REGION = (0.0, 0.10, 0.40, 0.95)

# Garage screen
PRESET_TITLE_REGION = (0.07, 0.48, 0.27, 0.535)
PRESET_PREV_ARROW = (0.0685, 0.507)
PRESET_NEXT_ARROW = (0.265, 0.507)
PRESET_RENAME_PENCIL = (0.230, 0.602)
# Garage buttons, used when the text reader misses their labels (seen live). Measured at 2560x1440.
CUSTOMIZE_CAR_BUTTON = (0.123, 0.557)
CREATE_PRESET_BUTTON = (0.123, 0.601)
# The preset DELETE bin sits right of the pencil. The app refuses to click anywhere in this box
# while on the garage screen, except from the "Clear all presets" job after the user confirmed it.
DELETE_BIN_ZONE = (0.244, 0.570, 0.275, 0.635)
DELETE_BIN = (0.2555, 0.602)
# "DELETE PRESET / Are you sure you want to delete this preset? / YES  NO", measured live at 2560x1440.
# The short button words only read reliably from a tight crop.
DELETE_BUTTONS_REGION = (0.38, 0.535, 0.62, 0.585)
# RENAME PRESET dialog (centre of screen), measured live at 2560x1440
DIALOG_REGION = (0.30, 0.38, 0.70, 0.62)
RENAME_TEXT_BOX = (0.4014, 0.5075)
PRESET_NAME_MAX = 20

# Customize screen
TAB_LEFT_ARROW = (0.070, 0.135)
TAB_RIGHT_ARROW = (0.3435, 0.135)
PANEL_TITLE_REGION = (0.060, 0.165, 0.245, 0.240)
FILTER_BUTTON_REGION = (0.245, 0.170, 0.350, 0.215)
FILTER_BUTTON = (0.297, 0.193)
CLEAR_FILTERS_REGION = (0.245, 0.210, 0.350, 0.245)  # only shown while a search/filter is active
SEARCH_BOX = (0.1575, 0.2756)
SEARCH_TEXT_REGION = (0.065, 0.258, 0.235, 0.293)
GRID_REGION = (0.060, 0.25, 0.340, 0.81)
BOTTOM_BUTTONS_REGION = (0.05, 0.88, 0.40, 0.94)

# Item grid: 4 columns x 4 visible rows. Points are the centre of each tile's name text.
GRID_COLUMNS_X = (0.0993, 0.1669, 0.2344, 0.3019)
GRID_ROWS_NAME_Y = (0.3698, 0.5073, 0.6451, 0.7829)
TILE_HALF_WIDTH = 0.0318
TILE_TEXT_ABOVE_NAME = 0.034   # paint badge sits just above the name
TILE_TEXT_BELOW_NAME = 0.015
BADGE_ABOVE_NAME = 0.040        # paint badge strip, read separately with contrast boost
BADGE_BELOW_NAME = 0.010
GRID_SCROLL_POINT = (0.20, 0.60)

# Paint finish tab
FINISH_LIST_REGION = (0.200, 0.280, 0.335, 0.860)  # accent list opens lower than primary
FINISH_LIST_SCROLL_POINT = (0.265, 0.55)

# Colour swatches left of the finish buttons. Clicking one opens a grid of squares just below it:
# 10 x 7 for primary (team hues), 15 x 7 for accent. The sheet's colour pictures are the same grids.
# Their rows are found on screen (paint_rows) because some decals remove the ACCENT rows.
PAINT_ROWS_REGION = (0.06, 0.26, 0.34, 0.56)
COLOUR_SWATCH_X = 0.166
FINISH_BUTTON_X = 0.2561
COLOUR_GRID_LEFT = 0.1355
COLOUR_GRID_TOP_BELOW_SWATCH = 0.0213
COLOUR_CELL = (0.01418, 0.0255)  # width, height of one square
COLOUR_GRID_COLUMNS = {"primary": 10, "accent": 15}
COLOUR_GRID_ROWS = 7

# Panel titles for each tab, in the order the tab arrows step through them.
TABS = [
    ("body", ["BODY"]),
    ("decal", ["DECAL"]),
    ("paint_finish", ["PAINT FINISH"]),
    ("wheels", ["WHEELS"]),
    ("boost", ["ROCKET BOOST", "BOOST"]),
    ("topper", ["TOPPER"]),
    ("antenna", ["ANTENNA"]),
    ("goal_explosion", ["GOAL EXPLOSION"]),
    ("trail", ["TRAIL"]),
    ("engine_audio", ["ENGINE AUDIO"]),
]

# Free items every player owns, used when "use default item" is on and the pro's item isn't owned.
DEFAULT_ITEMS = {
    "body": "Octane",
    "decal": "None",
    "wheels": "OEM",
    "boost": "Standard",
    "trail": "Classic",
    "goal_explosion": "Classic",
}

# Paint finish to use when the pro's finish isn't owned (user's choice). None = leave it as it is.
DEFAULT_FINISH = "Glossy"

PAINTS = [
    "Black", "Burnt Sienna", "Cobalt", "Crimson", "Forest Green", "Gold", "Grey",
    "Lime", "Orange", "Pink", "Purple", "Saffron", "Sky Blue", "Titanium White",
]
