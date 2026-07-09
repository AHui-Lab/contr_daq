import numpy as np


def downsample_xy(x, y, max_points):
    x = np.asarray(x)
    y = np.asarray(y)
    max_points = int(max_points)

    if max_points <= 0 or len(y) <= max_points:
        return x, y

    if max_points < 4:
        indices = np.linspace(0, len(y) - 1, max_points, dtype=int)
        return x[indices], y[indices]

    bin_count = max(1, max_points // 2)
    edges = np.linspace(0, len(y), bin_count + 1, dtype=int)
    indices = {0, len(y) - 1}

    for start, stop in zip(edges[:-1], edges[1:]):
        if stop <= start:
            continue

        segment = y[start:stop]
        indices.add(start + int(np.argmin(segment)))
        indices.add(start + int(np.argmax(segment)))

    ordered = np.array(sorted(indices), dtype=int)
    if len(ordered) > max_points:
        keep = np.linspace(0, len(ordered) - 1, max_points, dtype=int)
        ordered = ordered[keep]

    return x[ordered], y[ordered]
