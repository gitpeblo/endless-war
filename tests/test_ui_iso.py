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
