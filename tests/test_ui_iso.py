from endless_war.ui.iso import (
    BORDER,
    STEP_X,
    STEP_Y,
    board_for,
    draw_order,
    face_centre,
    province_at,
    tile_origin,
)


def test_the_scale_is_the_largest_integer_that_fits() -> None:
    # 12 x 8 provinces plus the water ring is 576 x 316 unscaled.
    assert board_for(96, 12, 600, 400).scale == 1
    assert board_for(96, 12, 1400, 800).scale == 2
    assert board_for(96, 12, 1800, 1000).scale == 3


def test_the_scale_never_drops_below_one() -> None:
    assert board_for(96, 12, 50, 30).scale == 1
    assert board_for(96, 12, 0, 0).scale == 1


def test_the_board_is_centred() -> None:
    small, big = board_for(96, 12, 600, 400), board_for(96, 12, 800, 400)
    assert big.origin_x - small.origin_x == 100  # 200 px wider, same scale


def test_tiles_step_isometrically() -> None:
    for scale_size in ((600, 400), (1400, 800)):
        board = board_for(96, 12, *scale_size)
        x0, y0 = tile_origin(board, 0, 0)
        x1, y1 = tile_origin(board, 1, 0)
        x2, y2 = tile_origin(board, 0, 1)
        assert (x1 - x0, y1 - y0) == (STEP_X * board.scale, STEP_Y * board.scale)
        assert (x2 - x0, y2 - y0) == (-STEP_X * board.scale, STEP_Y * board.scale)


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


def test_the_whole_board_fits_inside_the_widget() -> None:
    for size in ((600, 400), (980, 640), (1400, 800)):
        board = board_for(96, 12, *size)
        xs, ys = [], []
        for c, r in draw_order(12, 8):
            x, y = tile_origin(board, c, r)
            xs += [x, x + 48 * board.scale]
            ys += [y, y + (48 + 4) * board.scale]
        assert min(xs) >= 0 and max(xs) <= size[0], size
        assert min(ys) >= 0 and max(ys) <= size[1], size


from endless_war.ui.iso import (  # noqa: E402
    KEEP_VISIBLE,
    MAX_SCALE,
    Camera,
    board_with,
    pan_by,
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


def test_the_board_cannot_be_dragged_out_of_sight() -> None:
    for dx, dy in ((10_000, 0), (-10_000, 0), (0, 10_000), (0, -10_000)):
        camera = pan_by(96, 12, *SIZE, Camera(4, 0.0, 0.0), dx, dy)
        board = board_with(96, 12, *SIZE, camera)
        xs, ys = [], []
        for c, r in draw_order(12, 8):
            x, y = tile_origin(board, c, r)
            xs += [x, x + 48 * board.scale]
            ys += [y, y + 52 * board.scale]
        assert max(xs) >= KEEP_VISIBLE and min(xs) <= SIZE[0] - KEEP_VISIBLE, (dx, dy)
        assert max(ys) >= KEEP_VISIBLE and min(ys) <= SIZE[1] - KEEP_VISIBLE, (dx, dy)
