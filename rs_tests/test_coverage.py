"""The minimap's painting. PIL only - no display and no Tk."""

import math

import pytest

from rs_core import coverage, measure, palette

RADIUS = 1352744.5            # A 2 in Col 285 Sector LS-P b7-1, from a sidecar
LAT, LON = 53.259235, -178.692352


def at(x, y):
    """(lat, lon) x metres east and y metres north of LAT, LON."""
    scale = measure.metres_per_degree(RADIUS)
    return LAT + y / scale, LON + x / (scale * math.cos(math.radians(LAT)))


def status(x=0.0, y=0.0, body="A 2", flags=coverage.IN_SRV, heading=90):
    lat, lon = at(x, y)
    return {"Flags": flags, "BodyName": body, "Latitude": lat, "Longitude": lon,
            "PlanetRadius": RADIUS, "Heading": heading}


def fresh():
    return coverage.Coverage("A 2", LAT, LON, RADIUS)


def disc_km2():
    return math.pi * (coverage.SCAN_RADIUS_M / 1000.0) ** 2


@pytest.mark.unit
class TestFix:

    def test_in_the_srv_gives_a_fix(self):
        body, lat, lon, radius, heading = coverage.srv_fix(status())
        assert (body, radius, heading) == ("A 2", RADIUS, 90)

    def test_in_the_ship_gives_none(self):
        assert coverage.srv_fix(status(flags=0x1000000)) is None

    def test_in_the_srv_without_coordinates_gives_none(self):
        reading = status()
        del reading["Latitude"]
        assert coverage.srv_fix(reading) is None

    def test_an_empty_read_gives_none(self):
        assert coverage.srv_fix({}) is None


@pytest.mark.unit
class TestPainting:

    def test_one_stamp_is_one_disc(self):
        cover = fresh()
        cover.add(*at(0, 0))
        # A 40 px disc rasterised comes out 2.4% over the true circle.
        assert cover.painted_km2() == pytest.approx(disc_km2(), rel=0.03)

    def test_a_drive_paints_a_strip_not_a_row_of_dots(self):
        cover = fresh()
        for step in range(0, 4001, 30):
            cover.add(*at(step, 0))
        # A 4 km stadium: the strip between the end discs plus one disc.
        strip = 4.0 * 2 * coverage.SCAN_RADIUS_M / 1000.0
        assert cover.painted_km2() == pytest.approx(strip + disc_km2(), rel=0.03)

    def test_driving_back_over_painted_ground_changes_nothing(self):
        cover = fresh()
        for step in range(0, 4001, 30):
            cover.add(*at(step, 0))
        version, area = cover.version, cover.painted_km2()
        for step in range(4000, -1, -30):
            cover.add(*at(step, 0))
        assert (cover.version, cover.painted_km2()) == (version, area)

    def test_new_ground_moves_the_version(self):
        cover = fresh()
        cover.add(*at(0, 0))
        version = cover.version
        cover.add(*at(0, 3000))
        assert cover.version == version + 1

    def test_outside_the_mask_is_not_painted(self):
        cover = fresh()
        assert cover.add(*at(coverage.REACH_M + 500, 0)) is False
        assert cover.painted_km2() == 0

    def test_the_mask_edge_paints_only_what_is_inside(self):
        cover = fresh()
        # A metre inside: exactly on REACH_M is a float's width either side.
        cover.add(*at(coverage.REACH_M - 1, 0))
        assert cover.painted_km2() == pytest.approx(disc_km2() / 2, rel=0.05)

    def test_stamping_the_mask_edge_again_is_not_new_ground(self):
        # A crop past the edge used to count its zero padding as new paint,
        # and rebuild the layer on every stamp out there.
        cover = fresh()
        edge = coverage.REACH_M - 1000
        cover.add(*at(edge, 0))
        version = cover.version
        for _ in range(5):
            cover.launched(*at(edge, 0))
            cover.add(*at(edge, 0))
        assert cover.version == version

    def test_crossing_the_180th_meridian_is_a_step_not_a_planet(self):
        cover = coverage.Coverage("A 2", LAT, 179.99, RADIUS)
        x, _ = cover.xy(LAT, -179.99)
        assert 0 < x < 1000
        assert cover.add(LAT, -179.99) is True


@pytest.mark.unit
class TestFollow:

    def fix(self, **kwargs):
        return coverage.srv_fix(status(**kwargs))

    def test_the_first_launch_is_the_droppoint(self):
        cover = coverage.follow(None, self.fix(x=100, y=200), was_in_srv=False)
        assert cover.xy(*at(100, 200)) == pytest.approx((0, 0), abs=0.01)

    def test_a_ship_hop_inside_the_mask_keeps_the_map(self):
        cover = coverage.follow(None, self.fix(), was_in_srv=False)
        cover.add(*at(0, 0))
        again = coverage.follow(cover, self.fix(x=3300), was_in_srv=False)
        assert again is cover

    def test_a_launch_outside_the_mask_is_a_new_droppoint(self):
        cover = coverage.follow(None, self.fix(), was_in_srv=False)
        again = coverage.follow(cover, self.fix(x=coverage.REACH_M + 1000), was_in_srv=False)
        assert again is not cover

    def test_driving_out_of_the_mask_keeps_the_map(self):
        cover = coverage.follow(None, self.fix(), was_in_srv=False)
        again = coverage.follow(cover, self.fix(x=coverage.REACH_M + 1000), was_in_srv=True)
        assert again is cover

    def test_a_relaunch_moves_the_droppoint_to_where_the_ship_is_now(self):
        cover = coverage.follow(None, self.fix(), was_in_srv=False)
        cover = coverage.follow(cover, self.fix(x=3300, y=-500), was_in_srv=False)
        cover = coverage.follow(cover, self.fix(x=3400, y=-400), was_in_srv=True)
        assert tuple(round(v) for v in cover.anchor()) == (3300, -500)

    def test_the_ship_hop_itself_paints_nothing(self):
        # Only fixes in the SRV reach add(); the flight between two launches
        # leaves the ground between them unpainted.
        cover = coverage.follow(None, self.fix(), was_in_srv=False)
        cover.add(*at(0, 0))
        cover = coverage.follow(cover, self.fix(x=6000), was_in_srv=False)
        cover.add(*at(6000, 0))
        assert cover.painted_km2() == pytest.approx(2 * disc_km2(), rel=0.03)

    def test_another_body_is_a_new_droppoint(self):
        cover = coverage.follow(None, self.fix(), was_in_srv=True)
        assert coverage.follow(cover, self.fix(body="A 3"), was_in_srv=True) is not cover

    def test_a_relaunch_paints_at_once_rather_than_waiting_for_a_stamp_step(self):
        cover = coverage.follow(None, self.fix(), was_in_srv=False)
        cover.add(*at(0, 0))
        cover.add(*at(coverage.STAMP_M * 0.5, 0))    # too close: skipped
        version = cover.version
        # 200 m on: new ground, but closer than a stamp step to the last disc.
        cover.add(*at(0, 200))
        assert cover.version == version
        coverage.follow(cover, self.fix(y=200), was_in_srv=False)
        cover.add(*at(0, 200))
        assert cover.version == version + 1


def drive(cover, track):
    """Fixes along the track, at the six decimals Status.json gives. A saved
    point is rounded to six, so finer input would repaint a few edge pixels
    differently - 3 of 774,400 when this was not rounded."""
    for (x1, y1), (x2, y2) in zip(track, track[1:]):
        steps = int(math.hypot(x2 - x1, y2 - y1) // 30)
        for i in range(steps + 1):
            lat, lon = at(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
            cover.add(round(lat, 6), round(lon, 6))


@pytest.mark.unit
class TestSaved:

    def fix(self, **kwargs):
        return coverage.srv_fix(status(**kwargs))

    def driven(self):
        cover = coverage.follow(None, self.fix(), was_in_srv=False)
        drive(cover, [(0, 0), (6000, 2000), (3000, -5000), (-4000, -1000)])
        cover.launched(*at(5000, 5000))
        drive(cover, [(5000, 5000), (9000, 8000)])
        return cover

    def test_the_points_repaint_the_same_mask(self):
        cover = self.driven()
        back = coverage.Coverage.from_dict("A 2", cover.to_dict(), "map 1")
        assert back.mask.tobytes() == cover.mask.tobytes()
        assert back.name == "map 1" and "drops" not in cover.to_dict()

    def test_only_new_ground_is_kept(self):
        cover = fresh()
        drive(cover, [(0, 0), (4000, 0), (0, 0)])
        # Out and back: the way back paints nothing new.
        stamps = len(cover.stamps)
        drive(cover, [(0, 0), (4000, 0)])
        assert len(cover.stamps) == stamps

    def test_not_a_map_is_none(self):
        assert coverage.Coverage.from_dict("A 2", {"origin": "x"}) is None
        assert coverage.Coverage.from_dict("A 2", {}) is None

    def test_a_launch_within_reach_carries_the_saved_map_on(self):
        cover = self.driven()
        saved = lambda body: [("map 1", cover.to_dict())] if body == "A 2" else []
        again = coverage.follow(None, self.fix(x=8000, y=-3000), was_in_srv=False, saved=saved)
        assert again.name == "map 1"
        assert again.painted_km2() == pytest.approx(cover.painted_km2())
        assert tuple(round(v) for v in again.anchor()) == (8000, -3000)

    def test_a_launch_out_of_reach_is_a_new_map(self):
        cover = self.driven()
        saved = lambda body: [("map 1", cover.to_dict())]
        again = coverage.follow(None, self.fix(x=coverage.REACH_M + 1000), was_in_srv=False,
                                saved=saved)
        assert again.name is None and again.painted_km2() == 0

    def test_the_nearest_saved_map_wins(self):
        near = coverage.Coverage("A 2", *at(2000, 0), RADIUS)
        far = coverage.Coverage("A 2", *at(-8000, 0), RADIUS)
        saved = lambda body: [("map 1", far.to_dict()), ("map 2", near.to_dict())]
        assert coverage.follow(None, self.fix(), was_in_srv=False, saved=saved).name == "map 2"

    def test_the_last_saved_map_wins_over_the_nearest(self):
        # What EDMC would have had in memory, so a restart does not split the
        # ground across two files.
        near = dict(coverage.Coverage("A 2", *at(2000, 0), RADIUS).to_dict(), saved=100.0)
        far = dict(coverage.Coverage("A 2", *at(-8000, 0), RADIUS).to_dict(), saved=200.0)
        saved = lambda body: [("map 1", near), ("map 2", far)]
        assert coverage.follow(None, self.fix(), was_in_srv=False, saved=saved).name == "map 2"

    def test_a_nearest_map_that_will_not_load_gives_way(self):
        near = dict(coverage.Coverage("A 2", *at(2000, 0), RADIUS).to_dict(), stamps="broken")
        far = coverage.Coverage("A 2", *at(-8000, 0), RADIUS).to_dict()
        saved = lambda body: [("map 1", far), ("map 2", near)]
        assert coverage.follow(None, self.fix(), was_in_srv=False, saved=saved).name == "map 1"

    def test_a_point_belongs_to_the_map_with_the_nearest_origin(self):
        near = coverage.Coverage("A 2", *at(2000, 0), RADIUS).to_dict()
        far = coverage.Coverage("A 2", *at(-8000, 0), RADIUS).to_dict()
        found = [("map 1", far), ("map 2", near)]
        assert coverage.map_at(found, "A 2", *at(0, 0)) == "map 2"
        assert coverage.map_at(found, "A 2", *at(coverage.REACH_M + 5000, 0)) is None

    def test_mapped_locations_from_the_stored_location_and_from_bookmarks(self):
        targeted = dict(coverage.Coverage("A 2", *at(-8000, 0), RADIUS).to_dict(), location=3)
        driven = coverage.Coverage("A 2", *at(2000, 0), RADIUS).to_dict()
        elsewhere = coverage.Coverage("A 2", *at(0, 200000), RADIUS).to_dict()
        found = [("map 1", targeted), ("map 10", driven), ("map 2", elsewhere)]
        lat, lon = at(0, 0)
        records = [{"location_index": 7, "latitude": lat, "longitude": lon},
                   {"location_index": None, "latitude": lat, "longitude": lon},
                   {"location_index": 9}]
        mapped, unknown = coverage.mapped_locations(found, "A 2", records)
        assert mapped == {3: ["map 1"], 7: ["map 10"]}
        assert unknown == ["map 2"]

    def test_no_maps_no_locations(self):
        assert coverage.mapped_locations([], "A 2", [{"location_index": 1,
                                                      "latitude": 0, "longitude": 0}]) == ({}, [])

    def test_centring_moves_the_map_and_keeps_the_ground(self):
        cover = self.driven()
        area = cover.painted_km2()
        cover.recenter(*at(3000, 1000))
        assert cover.centered and cover.anchor() == (0.0, 0.0)
        # All of the drive lies within reach of the new centre, so nothing is lost.
        assert cover.painted_km2() == pytest.approx(area, rel=0.02)
        assert cover.xy(*at(3000, 1000)) == pytest.approx((0, 0), abs=0.5)

    def test_a_centre_is_saved_and_comes_back(self):
        cover = self.driven()
        # Six decimals, as the hotkey takes it from Status.json.
        centre = [round(v, 6) for v in at(3000, 1000)]
        cover.recenter(*centre)
        data = cover.to_dict()
        assert data["center"] == centre
        back = coverage.Coverage.from_dict("A 2", data, "map 1")
        assert back.centered and back.mask.tobytes() == cover.mask.tobytes()

    def test_an_uncentred_map_saves_no_centre(self):
        assert "center" not in self.driven().to_dict()

    def test_points_past_a_new_centres_reach_stay_on_disk(self):
        cover = self.driven()
        stamps = len(cover.stamps)
        cover.recenter(*at(-9000, -9000))
        assert len(cover.stamps) == stamps

    def test_a_border_needs_a_centre(self):
        cover = self.driven()
        assert cover.set_border(*at(3000, 0)) is False
        assert cover.border_m is None and "border_m" not in cover.to_dict()

    def test_a_border_is_its_distance_from_the_centre(self):
        cover = self.driven()
        cover.recenter(*[round(v, 6) for v in at(1000, 1000)])
        assert cover.set_border(*at(1000 + 3000, 1000 + 4000)) is True
        # A few metres off 5000: the test's own projection is centred on LAT, the
        # map's on the new centre a kilometre away.
        assert cover.border_m == pytest.approx(5000, abs=5)
        back = coverage.Coverage.from_dict("A 2", cover.to_dict(), "map 1")
        assert back.border_m == pytest.approx(cover.border_m, abs=1)

    def test_the_border_is_drawn_bold_around_the_centre(self):
        cover = fresh()
        cover.recenter(LAT, LON)
        cover.set_border(*at(0, 4500))
        side = 240
        per_m = side / (2 * coverage.VIEW_M)
        image = coverage.render(cover, 0, 0, None, side)
        # Straight south of the centre at 4.5 km, where no ring or grid line is.
        column = [image.getpixel((int(side / 2 + 250 * per_m), int(side / 2 + 4500 * per_m) + k))
                  for k in (-1, 0, 1)]
        assert coverage.BORDER in column

    def test_two_rings_round_the_centre_without_a_border(self):
        assert coverage.ring_radii() == [3750, 5500]

    def test_rings_run_out_until_one_scans_to_the_border(self):
        # 3.75 km scans to 5.75: a 5.66 km border needs no second ring.
        assert coverage.ring_radii(5659) == [3750]
        assert coverage.ring_radii(7000) == [3750, 5500]
        # 9.5 km: 7.25 scans to 9.25, one more at 9.0 reaches past it.
        assert coverage.ring_radii(9500) == [3750, 5500, 7250, 9000]

    def test_rings_are_counted_from_the_centre_not_the_border(self):
        for border in (4000, 6500, 8800):
            assert coverage.ring_radii(border)[0] == 3750

    def test_ground_outside_the_border_is_deleted(self):
        cover = fresh()
        drive(cover, [(0, 0), (8000, 0)])
        stamps = len(cover.stamps)
        cover.recenter(LAT, LON)
        cover.set_border(*at(0, 4000))
        assert len(cover.stamps) < stamps
        assert all(math.hypot(*cover.xy(*p)) <= 4000 for p in cover.stamps)
        # Nothing painted past the border, not even the edge of a disc inside it.
        per_px = coverage.MASK_M_PER_PX
        cx, cy = coverage._mask_px(0, 0)
        assert cover.mask.getpixel((int(cx + 4500 / per_px), int(cy))) == 0
        assert cover.mask.getpixel((int(cx + 3000 / per_px), int(cy))) == 255
        assert "stamps" in cover.to_dict() and len(cover.to_dict()["stamps"]) == len(cover.stamps)

    def test_driving_outside_the_border_paints_nothing(self):
        cover = fresh()
        cover.recenter(LAT, LON)
        cover.set_border(*at(0, 3000))
        version = cover.version
        assert cover.add(*at(6000, 0)) is True
        assert cover.version == version and cover.painted_km2() == 0

    def test_another_bodys_map_of_the_same_name_is_not_skipped(self):
        # 'map 1' on A 3 and 'map 1' on A 2 are different files.
        other = coverage.follow(None, self.fix(body="A 3"), was_in_srv=False)
        other.name = "map 1"
        saved = lambda body: [("map 1", fresh().to_dict())] if body == "A 2" else []
        assert coverage.follow(other, self.fix(), was_in_srv=True, saved=saved).name == "map 1"

    def test_the_picture_is_the_whole_mask_at_mask_size(self):
        cover = self.driven()
        image = coverage.picture(cover.mask.copy())
        assert image.size == (coverage.MASK_PX, coverage.MASK_PX)


@pytest.mark.unit
class TestScale:

    def test_a_1080p_window_gets_the_designed_map(self):
        assert coverage.map_side(1080) == 238

    def test_small_and_huge_windows_are_clamped(self):
        assert coverage.map_side(400) == coverage.MAP_MIN_PX
        assert coverage.map_side(4320) == coverage.MAP_MAX_PX

    def test_no_game_window_still_gets_a_map(self):
        assert coverage.MAP_MIN_PX <= coverage.map_side(None) <= coverage.MAP_MAX_PX

    def test_the_size_hotkey_grows_the_map(self):
        for height in (720, 1080, 1440):
            sides = [coverage.map_side(height, step) for step in coverage.MAP_ZOOMS]
            assert sides == sorted(sides) and sides[0] < sides[-1]

    def test_asking_for_bigger_goes_past_the_map_of_its_own_accord(self):
        assert coverage.map_side(4320, 1.8) > coverage.MAP_MAX_PX

    def test_the_biggest_the_hotkey_can_ask_for_is_bounded(self):
        # _draw_layer is redone on the Tk thread while driving, and it grows
        # with the square of the side.
        for height in (400, 720, 1080, 1440, 2160, 4320):
            for step in coverage.MAP_ZOOMS:
                assert coverage.map_side(height, step) <= coverage.MAP_ZOOM_MAX_PX

    def test_the_size_hotkey_works_without_a_game_window(self):
        assert coverage.map_side(None, 1.8) > coverage.map_side(None)


@pytest.mark.unit
class TestRender:

    def pixel(self, image, x, y):
        return image.getpixel((int(x), int(y)))

    def test_the_map_is_the_size_asked_for(self):
        assert coverage.render(fresh(), 0, 0, 0, 240).size == (240, 240)

    def test_north_is_up(self):
        cover = fresh()
        cover.add(*at(0, 6000))                     # painted 6 km north
        side = 240
        image = coverage.render(cover, 0, 0, None, side)
        per_m = side / (2 * coverage.VIEW_M)
        # 500 m east and 4.5 km north: inside the disc and off every grid line.
        north = self.pixel(image, side / 2 + 500 * per_m, side / 2 - 4500 * per_m)
        south = self.pixel(image, side / 2 + 500 * per_m, side / 2 + 4500 * per_m)
        assert north == coverage.FILL
        assert south == palette.rgb(palette.BG)

    def test_a_bookmark_is_a_dot_where_it_is(self):
        side = 240
        per_m = side / (2 * coverage.VIEW_M)
        image = coverage.render(fresh(), 0, 0, None, side, marks=[(3000, -2000)])
        assert self.pixel(image, side / 2 + 3000 * per_m, side / 2 + 2000 * per_m) == coverage.MARK
        assert self.pixel(image, side / 2 - 3000 * per_m, side / 2 + 2000 * per_m) != coverage.MARK

    def test_a_bookmark_is_smaller_than_the_droppoint(self):
        side = 240
        image = coverage.render(fresh(), 5000, 0, None, side, marks=[(0, 0)])
        dot = sum(1 for i in range(side) for j in range(side)
                  if image.getpixel((i, j)) == coverage.MARK)
        diamond = (2 * side * 0.024) ** 2 / 2         # the latest droppoint's area
        assert 0 < dot < diamond

    def test_a_bookmark_carries_its_code_beside_it(self):
        side = 240

        def red(marks):
            image = coverage.render(fresh(), 0, 0, None, side, marks=marks)
            return sum(1 for i in range(side // 2, side) for j in range(side // 2 - 20, side // 2 + 20)
                       if image.getpixel((i, j)) == coverage.MARK)
        assert red([(1500, 0, "T")]) > red([(1500, 0)]) + 10

    def test_scan_range_rings_around_the_latest_droppoint(self):
        side = 240
        per_m = side / (2 * coverage.VIEW_M)
        image = coverage.render(fresh(), 0, 0, None, side)

        def ring_near(radius_m):
            # Along a diagonal, off the grid lines, a pixel either side.
            d = radius_m * per_m / math.sqrt(2)
            # Reduced from twice the size, so blended with the background.
            bg = palette.rgb(palette.BG)
            return any(self.pixel(image, side / 2 + d + k, side / 2 - d - k) != bg
                       for k in (-1, 0, 1))
        assert ring_near(3750) and ring_near(5500)
        assert not ring_near(4600)

    def test_the_picture_grows_for_title_and_legend(self):
        cover = fresh()
        bare = coverage.picture(cover.mask.copy())
        full = coverage.picture(cover.mask.copy(),
                                title=["8 b  -  r Velorum", "Rocky World", "map 1"],
                                legend=[("T", "Thortveitite  ·  loc 2  ·  2 rigs")])
        assert full.width == bare.width and full.height > bare.height + 60
        long = coverage.picture(cover.mask.copy(),
                                title=["A 2  -  Col 285 Sector LS-P b7-1 with a much longer name"])
        assert long.width > bare.width

    def test_a_depleted_bookmark_is_red_an_active_one_green(self):
        side = 240
        per_m = side / (2 * coverage.VIEW_M)
        image = coverage.render(fresh(), 0, 0, None, side,
                                marks=[(3000, -2000, "T", False), (-3000, -2000, "PL", True)])
        assert self.pixel(image, side / 2 + 3000 * per_m, side / 2 + 2000 * per_m) == coverage.MARK
        assert self.pixel(image, side / 2 - 3000 * per_m, side / 2 + 2000 * per_m) == coverage.MARK_DEPLETED

    def test_a_legend_row_can_say_depleted(self):
        # The plugin writes (code, text, depleted) rows; the picture must take them.
        cover = fresh()
        image = coverage.picture(cover.mask.copy(), title=["8 b"],
                                 legend=[("T", "Thortveitite", False), ("PL", "Platinum  ·  depleted", True)])
        assert image.height > coverage.MASK_PX

    def test_the_picture_carries_the_bookmarks(self):
        cover = fresh()
        image = coverage.picture(cover.mask.copy(), marks=[(4000, 4000)])
        scale = image.width / (2 * coverage.REACH_M)
        assert image.getpixel((int(image.width / 2 + 4000 * scale),
                               int(image.height / 2 - 4000 * scale))) == coverage.MARK

    def test_the_bearing_to_a_droppoint(self):
        assert coverage.bearing(0, 1000, 0, 0) == pytest.approx(180)
        assert coverage.bearing(1000, 0, 0, 0) == pytest.approx(270)
        assert coverage.bearing(-1000, -1000, 0, 0) == pytest.approx(45)

    def test_the_layer_is_kept_until_something_new_is_painted(self):
        cover = fresh()
        for step in range(0, 4001, 30):
            cover.add(*at(step, 0))
        first = cover.layer(240)
        cover.add(*at(2000, 0))                     # 2 km back: stamps, inside the strip
        assert cover.layer(240) is first
        cover.add(*at(0, 5000))
        assert cover.layer(240) is not first

    def centred(self):
        cover = fresh()
        cover.recenter(LAT, LON)
        return cover

    def count(self, image, colour, box=None):
        left, top, right, bottom = box or (0, 0, image.width, image.height)
        return sum(1 for i in range(left, right) for j in range(top, bottom)
                   if image.getpixel((i, j)) == colour)

    def around(self, side, cx, cy, reach=14):
        return (max(0, int(cx) - reach), max(0, int(cy) - reach),
                min(side, int(cx) + reach), min(side, int(cy) + reach))

    def test_a_set_centre_is_marked_where_it_is(self):
        side = 240
        per_m = side / (2 * coverage.VIEW_M)
        # The SRV 3 km east of the centre, so the centre is not under its marker.
        image = coverage.render(self.centred(), 3000, 0, None, side)
        box = self.around(side, side / 2 - 3000 * per_m, side / 2)
        assert self.count(image, coverage.CENTRE, box) > 0

    def test_a_centre_nobody_set_is_not_marked(self):
        side = 240
        per_m = side / (2 * coverage.VIEW_M)
        image = coverage.render(fresh(), 3000, 0, None, side)
        box = self.around(side, side / 2 - 3000 * per_m, side / 2)
        assert self.count(image, coverage.CENTRE, box) == 0

    def test_a_line_runs_from_the_centre_to_every_spot(self):
        side = 240
        marks = [(2000, 0), (-2000, 1000), (0, -2500)]
        image = coverage.render(self.centred(), 0, 0, None, side, marks=marks)
        assert self.count(image, coverage.LINE_CENTRE) > 0
        assert self.count(coverage.render(fresh(), 0, 0, None, side, marks=marks),
                          coverage.LINE_CENTRE) == 0

    def test_a_line_runs_from_a_spot_to_the_spot_nearest_it(self):
        side = 240
        # Two pairs, one in each corner: each spot's nearest is its partner, so
        # the two short lines are drawn and nothing crosses the middle. A spot
        # joined to every other spot would put a line straight through it.
        marks = [(-3000, -2000), (-2400, -2000), (3000, 2000), (2400, 2000)]
        image = coverage.render(fresh(), 0, 0, None, side, marks=marks)
        assert self.count(image, coverage.LINE_SPOT) > 0
        assert self.count(image, coverage.LINE_SPOT,
                          self.around(side, side / 2, side / 2, 30)) == 0

    def test_two_bookmarks_from_one_standing_position_are_not_joined(self):
        side = 240
        image = coverage.render(fresh(), 0, 0, None, side, marks=[(2000, 0), (2000, 0)])
        assert self.count(image, coverage.LINE_SPOT) == 0

    def test_a_bookmark_off_the_map_gets_no_line(self):
        side = 240
        # 400 km away: on the body, nowhere near the 12 km the map shows.
        image = coverage.render(self.centred(), 0, 0, None, side, marks=[(400000, 0)])
        assert self.count(image, coverage.LINE_CENTRE) == 0

    def test_a_line_carries_its_length(self):
        # The SRV sitting on the centre with one bookmark 2 km out: the short
        # line whose number used to be squeezed off the map altogether. Drawn
        # at 480 because at 240 an 8 px glyph is nearly all antialiasing and an
        # exact-colour count cannot see it.
        side = 480
        bare = coverage.render(self.centred(), 0, 0, None, side)
        marked = coverage.render(self.centred(), 0, 0, None, side, marks=[(2000, 0)])
        assert self.count(marked, coverage.CENTRE) > self.count(bare, coverage.CENTRE) + 20

    def test_one_spot_on_its_own_has_nothing_to_join(self):
        side = 240
        image = coverage.render(fresh(), 0, 0, None, side, marks=[(2000, 0)])
        assert self.count(image, coverage.LINE_SPOT) == 0

    def test_the_numbers_thin_out_rather_than_print_over_each_other(self):
        side = 480                    # at 240 the glyphs are mostly antialiasing
        # Two dozen bookmarks 1.5 km out - someone who maps every material on
        # the location rather than the ones worth driving to.
        crowd = [(1500 * math.cos(math.radians(a)), 1500 * math.sin(math.radians(a)))
                 for a in range(0, 360, 15)]

        def ink(marks):
            # The accent is the centre ring and the centre lines' numbers, so
            # the ring is subtracted to leave the numbers.
            return (self.count(coverage.render(self.centred(), 0, 0, None, side, marks=marks),
                               coverage.CENTRE)
                    - self.count(coverage.render(self.centred(), 0, 0, None, side),
                                 coverage.CENTRE))
        one, many = ink(crowd[:1]), ink(crowd)
        assert one > 0                          # a lone spot does get its number
        assert 0 < many < len(crowd) * one      # not two dozen numbers' worth of ink

    def test_nothing_drawn_lands_on_the_overlay_key(self):
        cover = fresh()
        for step in range(0, 6001, 250):
            cover.add(*at(step, step))
        image = coverage.render(cover, 3000, 3000, 45, 240)
        key = palette.rgb(coverage.arrow.KEY)
        raw = image.tobytes()
        assert all(tuple(raw[i:i + 3]) != key for i in range(0, len(raw), 3))


@pytest.mark.unit
class TestIds:

    def test_the_ids_go_to_disk_and_back(self):
        cover = coverage.Coverage("A 2", LAT, LON, RADIUS, system_address=111)
        cover.body_id = 7
        data = cover.to_dict()
        assert data["system_address"] == 111 and data["body_id"] == 7
        back = coverage.Coverage.from_dict("A 2", data, "map 1")
        assert (back.system_address, back.body_id) == (111, 7)

    def test_a_map_without_ids_writes_none(self):
        data = coverage.Coverage("A 2", LAT, LON, RADIUS).to_dict()
        assert "system_address" not in data and "body_id" not in data

    def test_a_same_named_body_in_another_system_is_a_new_map(self):
        fix = coverage.srv_fix(status())
        cover = coverage.follow(None, fix, was_in_srv=False, system_address=111)
        again = coverage.follow(cover, fix, was_in_srv=True, system_address=222)
        assert again is not cover and again.system_address == 222

    def test_the_same_system_keeps_the_map(self):
        fix = coverage.srv_fix(status())
        cover = coverage.follow(None, fix, was_in_srv=False, system_address=111)
        assert coverage.follow(cover, fix, was_in_srv=True, system_address=111) is cover
