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

    def test_a_relaunch_adds_a_droppoint_where_the_ship_is_now(self):
        cover = coverage.follow(None, self.fix(), was_in_srv=False)
        cover = coverage.follow(cover, self.fix(x=3300, y=-500), was_in_srv=False)
        cover = coverage.follow(cover, self.fix(x=3400, y=-400), was_in_srv=True)
        assert [tuple(round(v) for v in d) for d in cover.drops] == [(0, 0), (3300, -500)]

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
        flat = lambda drops: [v for drop in drops for v in drop]
        assert flat(back.drops) == pytest.approx(flat(cover.drops), abs=0.1)
        assert back.name == "map 1"

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
        assert len(again.drops) == len(cover.drops) + 1

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

    def test_another_bodys_map_of_the_same_name_is_not_skipped(self):
        # 'map 1' on A 3 and 'map 1' on A 2 are different files.
        other = coverage.follow(None, self.fix(body="A 3"), was_in_srv=False)
        other.name = "map 1"
        saved = lambda body: [("map 1", fresh().to_dict())] if body == "A 2" else []
        assert coverage.follow(other, self.fix(), was_in_srv=True, saved=saved).name == "map 1"

    def test_the_picture_is_the_whole_mask_at_mask_size(self):
        cover = self.driven()
        image = coverage.picture(cover.mask.copy(), list(cover.drops))
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

    def test_the_picture_carries_the_bookmarks(self):
        cover = fresh()
        image = coverage.picture(cover.mask.copy(), list(cover.drops), marks=[(4000, 4000)])
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

    def test_nothing_drawn_lands_on_the_overlay_key(self):
        cover = fresh()
        for step in range(0, 6001, 250):
            cover.add(*at(step, step))
        image = coverage.render(cover, 3000, 3000, 45, 240)
        key = palette.rgb(coverage.arrow.KEY)
        raw = image.tobytes()
        assert all(tuple(raw[i:i + 3]) != key for i in range(0, len(raw), 3))
