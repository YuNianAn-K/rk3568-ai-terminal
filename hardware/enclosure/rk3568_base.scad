// RK3568 Protective Base - Window Frame Style
// Board: 正点原子 ATK-DLRK3568, 180.2x140.2mm

// ======================== Parameters ========================

board_x = 180.2;
board_y = 140.2;

wall      = 5;       // wall thickness
base      = 4;       // bottom plate thickness
wall_h    = 43;      // total wall height (4mm base + 43mm wall = 47mm total)
base_h    = 12;      // solid base wall height
corner    = 15;      // corner pillar width
top_strip = 11;      // top connecting strip thickness (45 - 2 - 10 - 22 = 11mm)
clearance = 1;       // board-to-wall gap
corner_r  = 3;       // corner fillet radius

// Derived
inner_x = board_x + clearance * 2;
inner_y = board_y + clearance * 2;
outer_x = inner_x + wall * 2;
outer_y = inner_y + wall * 2;

// ======================== Modules ========================

module rounded_box(sx, sy, sz, r) {
    hull() {
        translate([r, r, 0])
            cylinder(h = sz, r = r, $fn = 30);
        translate([sx - r, r, 0])
            cylinder(h = sz, r = r, $fn = 30);
        translate([r, sy - r, 0])
            cylinder(h = sz, r = r, $fn = 30);
        translate([sx - r, sy - r, 0])
            cylinder(h = sz, r = r, $fn = 30);
    }
}

// ======================== Window Cutouts ========================
// Cut from the middle of each wall, leaving:
//   - solid bottom (base_h)
//   - solid top strip (top_strip)
//   - solid corner pillars (corner)

module window_cuts() {
    win_z_bot = base + base_h;          // window starts above base wall
    win_z_top = base + wall_h - top_strip; // window ends below top strip
    win_h = win_z_top - win_z_bot;

    // Top long side A
    translate([wall + corner, outer_y - wall - 0.5, win_z_bot])
        cube([inner_x - corner * 2, wall + 1, win_h]);

    // Bottom long side C
    translate([wall + corner, -0.5, win_z_bot])
        cube([inner_x - corner * 2, wall + 1, win_h]);

    // Left short side B
    translate([-0.5, wall + corner, win_z_bot])
        cube([wall + 1, inner_y - corner * 2, win_h]);

    // Right short side D
    translate([outer_x - wall - 0.5, wall + corner, win_z_bot])
        cube([wall + 1, inner_y - corner * 2, win_h]);
}

// ======================== Ventilation Holes ========================

module vent_holes() {
    slot_w = 60;
    slot_h = 3;
    n_slots = 3;
    gap = 12;
    start_x = (outer_x - n_slots * slot_w - (n_slots - 1) * gap) / 2;

    for (i = [0 : n_slots - 1]) {
        translate([start_x + i * (slot_w + gap), outer_y * 0.25, -0.5])
            cube([slot_w, slot_h, base + 1]);
        translate([start_x + i * (slot_w + gap), outer_y * 0.5, -0.5])
            cube([slot_w, slot_h, base + 1]);
        translate([start_x + i * (slot_w + gap), outer_y * 0.75, -0.5])
            cube([slot_w, slot_h, base + 1]);
    }
}

// ======================== Assembly ========================

difference() {
    rounded_box(outer_x, outer_y, base + wall_h, corner_r);
    // Inner cavity
    translate([wall, wall, base])
        cube([inner_x, inner_y, wall_h + 1]);
    // Window cutouts
    window_cuts();
    // Ventilation holes in bottom
    vent_holes();
}

// ======================== Dimensions ========================
// Outer: 192 x 152 x 75 mm
// Inner: 182 x 142 mm
// Base solid wall: 40mm high
// Window opening: ~150x110mm per side, 22mm tall
// Top strip: 11mm connecting all four walls
