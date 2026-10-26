# Rocket League garage layout

Notes from mapping the garage menus at 1440p (English). The numbers in brackets refer to the
screenshots used while mapping, which aren't included in the repo.

## Flow

1. **Main menu** (`01`): left column of buttons — PLAY, ITEM SHOP, ROCKET PASS, GARAGE, ...
2. **Garage** (`02`, `03`): preset name between `<` `>` arrows (e.g. "PRESET 2", "FEN BLUSTER INVIS").
   Buttons: CUSTOMIZE CAR, CREATE NEW PRESET (+ rename pencil, delete bin), TRADE IN,
   MANAGE INVENTORY, BLUEPRINTS. Bottom: BACK, VIEW BLUE CAR (switches shown team).
3. **Customize car** (`04`, `05`): tab strip of icons at top of the panel, with `<` `>` to scroll it.
   Tab order: Body, Decal, Paint Finish, Wheels, Boost, Topper (`15`), Antenna (`14`),
   Goal Explosion (`13`), Trail (`12`), Engine Audio (`11`). The strip scrolls so the selected tab
   stays visible, so tab positions move — find tabs by the panel title (BODY, TRAIL, ...) instead.

## Item grid (body, decal, wheels, boost, ...)

- 4 columns, scrolls vertically. Header shows "N COLLECTED".
- **Only owned items are listed**, so "user doesn't own it" = "not found in the list".
- Each tile: picture, item name in text at the bottom, optional paint badge above the name
  (BLACK, SKY BLUE, TITANIUM WHITE, ...). Each painted copy is its own tile.
- Equipped tile shows a tick. Hovering shows a tooltip with the full name and "EQUIP TO TEAM"
  (mouse button icon), so items can be set per team.
- **SHOW FILTERS opens a text search box** (`10`), plus dropdowns: SORT BY, QUALITY, ATTRIBUTES,
  PAINTS. Plan: type the item name, set PAINTS to the wanted paint, then click the first result
  whose name matches. **No result = user doesn't own it, skip.** Button then reads HIDE FILTERS.
- Long names wrap onto two lines ("Chromatic / Abberation", "Divine / Intervention").
- Some tiles are folders (RLCS '25, Community Flags, ...) — never click those.
- Engine Audio (`11`) is a plain text list, no filters. The sheet has no engine audio, so skip it.
- Tooltips (`05`, `13`) can cover the area right of the panel; move the mouse away before reading.

## Paint finish tab (`06`, `09`)

- Two blocks: BLUE TEAM and ORANGE TEAM, each with PRIMARY and ACCENT rows.
- Each row: colour swatch on the left, finish name button on the right.
- Finish list is alphabetical, scrolls, header "39 / 39 COLLECTED".

## Colour grids (`07`, `08`)

- Primary colour: small grid limited to the team's hues (blue team: greens to purples), about 9 x 7.
- Accent colour: full grid, about 15 x 7 (first column greys, then hues).
- Sheet has no colour data yet, so colours are not set for now.

## Input plan

- Use **mouse clicks** in menus (cursor is visible in the garage). Simpler and more exact than
  stepping through menus with keys, and no controller driver needed.

## Still needed

- Exact positions: the app will take its own full-resolution captures to calibrate, since the
  chat resizes screenshots to 2000px wide.
