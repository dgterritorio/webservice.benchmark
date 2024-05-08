from typing import Generator, Tuple
import random
import math


class BBoxError(ValueError):
    """Custom exception for bounding box errors."""

    pass


def generate_random_bbox(
    full_bbox_minx: float,
    full_bbox_miny: float,
    full_bbox_maxx: float,
    full_bbox_maxy: float,
    seed: int,
    area: float,
    ratio: float,
) -> Generator[Tuple[float, float, float, float], None, None]:
    """
    Generate a deterministic random sub-bounding box within a specified full extent bounding box.

    Parameters:
    - full_bbox_minx, full_bbox_miny, full_bbox_maxx, full_bbox_maxy (float): Coordinates of the full extent bounding box.
    - area (float): The area of the sub-bounding box in square kilometers (default is 10).
    - ratio (float): The width to height ratio of the sub-bounding box (default is 1.0, representing a square).
    - seed (int): Optional. A seed value for the random number generator to ensure deterministic output.

    Yields:
    - A tuple of floats representing the sub-bounding box in the format (minx, miny, maxx, maxy).

    Raises:
    - BBoxError: If the full bounding box dimensions or the specified area are invalid.
    """
    if seed is not None:
        random.seed(
            seed
        )  # Seed the random number generator to ensure deterministic output

    if full_bbox_maxx <= full_bbox_minx or full_bbox_maxy <= full_bbox_miny:
        raise BBoxError("Invalid full bounding box dimensions.")
    if area <= 0:
        raise BBoxError("Area must be greater than 0.")
    if ratio <= 0:
        raise BBoxError("Aspect ratio must be greater than 0.")

    height_km = math.sqrt(area / ratio)
    width_km = ratio * height_km
    side_length_x, side_length_y = (
        width_km * 1000,
        height_km * 1000,
    )  # Convert km to meters

    max_start_x = full_bbox_maxx - side_length_x
    max_start_y = full_bbox_maxy - side_length_y

    while True:
        random_start_x = random.uniform(full_bbox_minx, max_start_x)
        random_start_y = random.uniform(full_bbox_miny, max_start_y)

        yield (
            random_start_x,
            random_start_y,
            random_start_x + side_length_x,
            random_start_y + side_length_y,
        )


# Example of function usage and testing
if __name__ == "__main__":
    try:
        test1 = {"area": 5, "ratio": 1.2, "seed": 42}
        test1_result = (
            50106.69464503156,
            -311016.67483456887,
            52556.184387814734,
            -308975.43338224955,
        )
        bbox_generator = generate_random_bbox(
            -144205.734375, -326024.8125, 162129.09375, 276083.78125, **test1
        )
        assert test1_result == next(bbox_generator)

    except BBoxError as e:
        # TODO: Better exception
        print(f"Error generating bbox: {e}")
