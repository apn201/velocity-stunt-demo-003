# The prompt

This is the whole input the film was made from, as typed into Claude Code. No images or video were attached. The only other things I said in the session were "Commit the stunt folder and README changes" and the request to write these texts.

---

We need a third version. Fully procedural, all code-based, no-asset, photorealistis 30 second blender animation about a supercar tehcnical demo:

Here is a comprehensive breakdown for a 3D artist to recreate this stunt demo sequence in CGI, covering environment, lighting, vehicle geometry, particle effects, camera movement, HUD overlays, and animation keyframes.

1. Environment & Set Design

* Set Layout: A dark, pitch-black industrial test facility or nighttime outdoor proving ground. The ground plane is matte black tarmac/asphalt with visible wetness or subtle glossy reflections where lights hit.

* The Ramp / Quarter-Pipe:

   * Shape & Curve: A massive quarter-pipe structure on the right side of the frame. It starts flat on the ground, swoops upward in an arc, and curves past 90 degrees into an upside-down horizontal roof/lip at the top.

   * Ramp Material: Light grey modular concrete panels with a central painted white lane line.

   * Ramp Skeleton: Heavy industrial steel truss framework supporting the back and underside of the ramp.

   * Ramp Lighting: Bright, continuous, neon-red LED strips outlining the curved side profile edges of the ramp structure.

* Background Elements:

   * A fleet lineup of static vehicles parked on a low, red-edge-lit platform in select shots (a dark blue sedan, red crossover, white semi-truck, stainless-steel wedge truck).

   * Black void background with subtle ground fog/haze floating at shoe-height.

2. Lighting Setup

* Key Lighting: Pure black void environment (`#000000` dark sky/background). Contrast is extreme—high dynamic range (HDR) with blown-out highlights and crushed shadows.

* Ground Uplights: A row of intense, high-output stage spotlights placed in a line on the ground, angled upward at approximately 45 degrees towards center stage.

   * Light rays must be visible breaking through the air/smoke via volumetrics.

* Color Palette:

   * Primary Accent: Neon Crimson / Red (`#FF0033`) on the ramp edge strips, ground stage edges, and vehicle tail lamps.

   * Secondary Accent: Cool Daylight White (`#E6F2FF` to `#FFFFFF`) from stage uplights, car headlights, and dense cold-gas thruster plumes.

3. Vehicle Specifications & Materials

* Body Geometry: Ultra-minimalist, aggressive wedge shape sports car. Low nose, sharp angular beltlines, flush glass surfaces, and flat slab-sided doors.

* Car Paint/Finish: Satin pearl white / silver-white paint with anisotropic soft reflections.

* Trim & Underbody:

   * Lower side skirts, front lip splitter, and rear diffuser are matte dark charcoal / carbon composite.

   * Flat, enclosed undercarriage panel with visible dark access hatches and recessed nozzle ports.

* Wheels: Solid aerocover wheel discs (matte silver center with black rim).

* Light Elements:

   * Front: Ultra-thin horizontal LED lightbar running along the leading edge of the hood, flanked by two sharp headlight projector clusters.

   * Rear: Full-width thin red LED light bar across the rear tail.

4. Thruster Visual Effects (VFX)

* Physical Nature: Cold-gas high-pressure compressed air nozzles (not combustion/fire).

* Plume Aesthetics:

   * High-density, opaque white fog/vapor streams expanding as they exit the nozzles.

   * High-velocity core near the exhaust port, dispersing into turbulently churning volumetric clouds further down.

   * Slight blue/teal volumetric tint (`#A5D8EB`) near the high-velocity nozzle exit point due to air condensation/pressure drop.

* Nozzle Placement:

   * Underside (Vertical Lift): Four downward-pointing high-output nozzles located under the chassis (two behind front wheels, two ahead of rear wheels).

   * Sides / Rear (Attitude Control): Horizontal nozzles on the rear fascia and front/rear quarters shooting vapor sideways and backwards for yaw/pitch stabilization and rotation.

5. Sequence Breakdown & Shot List
Demo Phase 1: Ramp Drive & Suction (Downforce)

* Shot 1 (Wide Static / Tracking):

   * The vehicle accelerates rapidly toward the curved quarter-pipe ramp.

   * Upon hitting the curve, suction systems ground the chassis, sticking it to the vertical wall and driving inverted onto the top horizontal ceiling section of the ramp without slipping off.

   * Camera tracks horizontally at ground level.

Demo Phase 2: Inverted Ejection & Mid-Air Maneuvers ("The Kickflip")

* Shot 2 (Wide Side Profile):

   * The car leaves the top inverted edge of the ramp, falling freely into the air.

   * Downward and lateral thrusters fire in short, explosive bursts.

   * Vehicle Motion: The car performs a synchronized axial 360° roll ("kickflip") while floating in mid-air above the arena floor.

   * Side attitude thrusters blast vapor horizontally to snap the car's orientation flat.

Demo Phase 3: Vertical Hover & Cushion Landing

* Shot 3 (Front Low-Angle Eye Level):

   * The car levels out roughly 15 to 25 feet above the ground.

   * All four underbody vertical thrusters engage continuously.

   * Thick vertical white vapor columns strike the asphalt floor, creating a violent 360-degree radial ring of fog rolling outward across the ground.

* Shot 4 (Medium Profile / Landing):

   * As the car descends, the bottom thrusters flare continuously to dampen acceleration, allowing the suspension to absorb a soft touchdown.

Demo Phase 4: Sub-1 Second Launch

* Shot 5 (Fixed Wide Ground Shot):

   * The car comes to a complete rest.

   * Rear-facing high-pressure thrusters purge in a sudden burst alongside wheel torque, catapulting the car out of frame from 0 to 60 mph in under 1 second.

   * Motion blur on the vehicle should be extreme; keyframes should span only a few frames from standstill to exit.

6. HUD / Telemetry Motion Graphics Overlay
To mirror the telemetry interface shown in live streams, place 2D graphic overlays in screen-space:

* Lower Left Corner:

   * G-Force Gauge: Circular dial with a moving crosshair indicator and digital readout (`0.5 G` to `4.0+ G`).

   * Car Pitch/Roll Pitch indicator: Wireframe 3D icon of the car tilting dynamically with real-time motion.

* Lower Right Corner:

   * Top-Down Chassis Diagram: Schematic showing 4 wheels and nozzle status indicators.

   * Altitude Gauge: Circular readout displaying height in feet (`ALTITUDE 54.8 FT`).

* Graphics Style: Fine white vector lines, high contrast, clean technical sans-serif font.
