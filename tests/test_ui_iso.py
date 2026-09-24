import pytest

from endless_war.ui.iso import (
    BORDER,
    MIN_SCALE,
    STEP_X,
    STEP_Y,
    board_for,
    draw_order,
    face_centre,
    province_at,
    tile_origin,
)


def test_the_fitted_scale_fills_the_widget() -> None:
    # The fit is to the land alone: 12 x 8 provinces are 480 x 264 unscaled.
    # The sea ring around them may run off the edges (the user wanted the map
    # to open closer than a fit that included the sea).
    assert board_for(96, 12, 600, 400).scale == pytest.approx(min(600 / 480, 400 / 264))
    assert board_for(96, 12, 1400, 800).scale == pytest.approx(min(1400 / 480, 800 / 264))


def test_the_fitted_scale_has_a_floor() -> None:
    assert board_for(96, 12, 50, 30).scale == MIN_SCALE
    assert board_for(96, 12, 0, 0).scale == MIN_SCALE


def _land(cols: int = 12, rows: int = 8):
    return [cell for cell in draw_order(cols, rows) if 0 <= cell[0] < cols and 0 <= cell[1] < rows]


def test_the_board_is_centred() -> None:
    for size in ((600, 400), (800, 400), (1400, 800)):
        board = board_for(96, 12, *size)
        xs, ys = [], []
        for c, r in _land():
            x, y = tile_origin(board, c, r)
            xs += [x, x + 48 * board.scale]
            ys += [y, y + 48 * board.scale]
        assert abs((min(xs) + max(xs)) / 2 - size[0] / 2) <= 1, size
        assert abs((min(ys) + max(ys)) / 2 - size[1] / 2) <= 1, size


def test_tiles_step_isometrically() -> None:
    for scale_size in ((600, 400), (1400, 800)):
        board = board_for(96, 12, *scale_size)
        x0, y0 = tile_origin(board, 0, 0)
        x1, y1 = tile_origin(board, 1, 0)
        x2, y2 = tile_origin(board, 0, 1)
        assert (x1 - x0, y1 - y0) == pytest.approx((STEP_X * board.scale, STEP_Y * board.scale))
        assert (x2 - x0, y2 - y0) == pytest.approx((-STEP_X * board.scale, STEP_Y * board.scale))


def test_draw_order_is_back_to_front_and_includes_the_ring() -> None:
    order = draw_order(12, 8)
    assert len(order) == (12 + 2 * BORDER) * (8 + 2 * BORDER)
    depths = [c + r for c, r in order]
    assert depths == sorted(depths)
    assert (-1, -1) in order and (12, 8) in order


def test_every_province_round_trips_through_its_face_centre() -> None:
    for size in ((600, 400), (1400, 800), (1800, 1000), (313, 197)):
        board = board_for(96, 12, *size)
        for pid in range(96):
            x, y = face_centre(board, pid % 12, pid // 12)
            assert province_at(board, x, y, 96) == pid, (size, pid)


def test_points_off_the_board_hit_nothing() -> None:
    board = board_for(96, 12, 600, 400)
    assert province_at(board, 0, 0, 96) is None
    assert province_at(board, 599, 399, 96) is None
    x, y = face_centre(board, -1, 0)  # a water cell
    assert province_at(board, x, y, 96) is None


def test_all_the_land_fits_inside_the_widget() -> None:
    for size in ((600, 400), (980, 640), (1400, 800)):
        board = board_for(96, 12, *size)
        xs, ys = [], []
        for c, r in _land():
            x, y = tile_origin(board, c, r)
            xs += [x, x + 48 * board.scale]
            ys += [y, y + 48 * board.scale]
        assert min(xs) >= -1 and max(xs) <= size[0] + 1, size
        assert min(ys) >= -1 and max(ys) <= size[1] + 1, size


from endless_war.ui.iso import (  # noqa: E402
    KEEP_VISIBLE,
    MAX_SCALE,
    Camera,
    board_with,
    pan_by,
    refit,
    zoom_at,
)

SIZE = (600, 400)  # the board fits at scale 1 here


def test_no_camera_is_the_fitted_board() -> None:
    assert board_with(96, 12, *SIZE, None) == board_for(96, 12, *SIZE)


def test_zooming_in_keeps_the_province_under_the_cursor() -> None:
    fitted = board_for(96, 12, *SIZE)
    for pid in (0, 11, 45, 95):
        x, y = face_centre(fitted, pid % 12, pid // 12)
        camera = zoom_at(96, 12, *SIZE, None, x, y, +1)
        assert camera is not None and camera.scale == 2
        zoomed = board_with(96, 12, *SIZE, camera)
        assert province_at(zoomed, x, y, 96) == pid, pid
        zx, zy = face_centre(zoomed, pid % 12, pid // 12)
        assert abs(zx - x) <= 2 and abs(zy - y) <= 2, (pid, zx - x, zy - y)


def test_zooming_back_to_the_fitted_scale_recentres() -> None:
    x, y = face_centre(board_for(96, 12, *SIZE), 3, 2)
    camera = zoom_at(96, 12, *SIZE, None, x, y, +1)
    camera = pan_by(96, 12, *SIZE, camera, 40, -25)
    assert zoom_at(96, 12, *SIZE, camera, x, y, -1) is None


def test_zooming_out_past_the_fitted_scale_stays_fitted() -> None:
    assert zoom_at(96, 12, *SIZE, None, 300, 200, -1) is None


def test_zoom_stops_at_the_maximum() -> None:
    camera = Camera(MAX_SCALE, 0.0, 0.0)
    assert zoom_at(96, 12, *SIZE, camera, 300, 200, +1).scale == MAX_SCALE


def test_panning_moves_the_board_by_the_drag() -> None:
    before = board_for(96, 12, *SIZE)
    camera = pan_by(96, 12, *SIZE, None, 30, -20)
    after = board_with(96, 12, *SIZE, camera)
    assert (after.origin_x - before.origin_x, after.origin_y - before.origin_y) == (30, -20)


def _visible_face_centres(board, size) -> int:
    inside = 0
    for pid in range(96):
        x, y = face_centre(board, pid % 12, pid // 12)
        if 0 <= x <= size[0] and 0 <= y <= size[1]:
            inside += 1
    return inside


def test_the_board_cannot_be_dragged_out_of_sight() -> None:
    # The bounding box of a diamond board has empty corners: keeping part of
    # the box on screen still let the map vanish (final review, measured).
    for scale in (4, 8):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            camera = pan_by(96, 12, *SIZE, Camera(scale, 0.0, 0.0), dx * 50_000, dy * 50_000)
            board = board_with(96, 12, *SIZE, camera)
            assert _visible_face_centres(board, SIZE) >= 1, (scale, dx, dy)


def test_every_corner_can_still_be_reached_when_zoomed_in() -> None:
    for pid in (0, 11, 84, 95):
        camera = Camera(8, 0.0, 0.0)
        for _ in range(50):  # drag toward the corner province until it is centred
            board = board_with(96, 12, *SIZE, camera)
            x, y = face_centre(board, pid % 12, pid // 12)
            camera = pan_by(96, 12, *SIZE, camera, SIZE[0] / 2 - x, SIZE[1] / 2 - y)
        board = board_with(96, 12, *SIZE, camera)
        x, y = face_centre(board, pid % 12, pid // 12)
        assert abs(x - SIZE[0] / 2) <= 2 and abs(y - SIZE[1] / 2) <= 2, pid


def test_a_camera_is_refitted_when_the_widget_grows_past_it() -> None:
    camera = pan_by(96, 12, *SIZE, None, 40, 10)  # a pan at the fitted scale
    assert refit(96, 12, 1400, 800, camera) is None, "a bigger window must re-fit"
    zoomed = Camera(3, 0.0, 0.0)
    assert refit(96, 12, 1400, 800, zoomed).scale == 3, "a zoom above the new fit is kept"


def test_a_camera_is_reclamped_when_the_widget_shrinks() -> None:
    far = pan_by(96, 12, 1500, 900, Camera(3, 0.0, 0.0), 50_000, 0)
    shrunk = refit(96, 12, *SIZE, far)
    assert shrunk is not None
    assert _visible_face_centres(board_with(96, 12, *SIZE, shrunk), SIZE) >= 1


def test_zooming_in_from_a_fractional_fit_goes_to_the_next_whole_scale() -> None:
    fit = board_for(96, 12, 1400, 800).scale  # about 2.43
    camera = zoom_at(96, 12, 1400, 800, None, 700, 400, +1)
    assert camera.scale == 3 > fit
