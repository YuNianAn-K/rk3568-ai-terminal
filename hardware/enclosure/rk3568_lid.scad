// RK3568 Cap-Style Removable Lid
// Fits on top of rk3568_base (192x152mm outer, R3 corners)

// ======================== Parameters ========================

// Base dimensions (from rk3568_base.scad)
base_outer_x = 192;
base_outer_y = 152;
base_corner_r = 3;

// Lid parameters
lip_height   = 12;    // how far the lip drops down
lip_wall     = 2;     // lip wall thickness
plate_thick  = 2;     // top plate thickness
clearance    = 0.5;   // gap between lid inner and base outer per side
corner_r     = 3;     // corner fillet radius (match base)

// Derived
inner_x = base_outer_x + clearance * 2;
inner_y = base_outer_y + clearance * 2;
outer_x = inner_x + lip_wall * 2;
outer_y = inner_y + lip_wall * 2;
total_h = plate_thick + lip_height;

// ======================== Modules ========================

module rounded_rect(sx, sy, sz, r) {
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

// ======================== Assembly ========================

// Outer shell (full size)
difference() {
    // Solid outer block
    rounded_rect(outer_x, outer_y, total_h, corner_r);

    // Inner cavity (where base walls sit)
    translate([lip_wall, lip_wall, plate_thick])
        cube([inner_x, inner_y, lip_height + 1]);

    // Optional: center cutout on top plate to save material
    // Uncomment below for a lighter lid with a recessed window
    // translate([lip_wall + 5, lip_wall + 5, -0.5])
    //     rounded_rect(inner_x - 10, inner_y - 10, plate_thick + 1, 3);
}

// ======================== Dimensions ========================
// Outer: ~197 x 157 x 14 mm
// Inner cavity: 193 x 153 mm (0.5mm clearance per side from base)
// Lip height: 12mm (covers top strip + part of window)
// Top plate: 2mm thick
